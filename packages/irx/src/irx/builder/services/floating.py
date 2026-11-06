"""
title: Focused floating-point instruction flags and FMA intrinsic emission.
summary: >-
  Intrinsic identities belong to the LLVM module. The temporary fast-math flag
  belongs to the active operation/function and is restored by source handlers;
  it is never retained by immutable feature configuration.
"""

from collections.abc import Callable
from contextlib import contextmanager
from typing import Iterator

from llvmlite import ir
from llvmlite.ir import DoubleType, FloatType, HalfType
from public import private

from irx.builder.types import is_fp_type
from irx.typecheck import typechecked


@private
@typechecked
class FloatingEmission:
    """
    title: >-
      Emit representation-level floating instructions without semantic policy.
    attributes:
      module:
        type: ir.Module
      builder:
        type: Callable[[], ir.IRBuilder]
      enabled:
        type: bool
    """

    module: ir.Module
    builder: Callable[[], ir.IRBuilder]
    enabled: bool

    def __init__(
        self, module: ir.Module, builder: Callable[[], ir.IRBuilder]
    ) -> None:
        """
        title: Bind one module and the active function's instruction builder.
        parameters:
          module:
            type: ir.Module
          builder:
            type: Callable[[], ir.IRBuilder]
        """
        self.module = module
        self.builder = builder
        self.enabled = False

    @contextmanager
    def function_scope(self) -> Iterator[None]:
        """
        title: Isolate temporary flags across nested generated functions.
        returns:
          type: Iterator[None]
        """
        previous = self.enabled
        self.enabled = False
        try:
            yield
        finally:
            self.enabled = previous

    def get_fma_function(self, ty: ir.Type) -> ir.Function:
        """
        title: Get fma function.
        parameters:
          ty:
            type: ir.Type
        returns:
          type: ir.Function
        """
        if isinstance(ty, ir.VectorType):
            elem_ty = ty.element
            count = ty.count
        else:
            elem_ty = ty
            count = None

        if isinstance(elem_ty, FloatType):
            suffix = "f32"
        elif isinstance(elem_ty, DoubleType):
            suffix = "f64"
        elif isinstance(elem_ty, HalfType):
            suffix = "f16"
        else:
            raise TypeError("FMA supports only floating-point operands")

        if count is not None:
            suffix = f"v{count}{suffix}"

        name = f"llvm.fma.{suffix}"
        existing = self.module.globals.get(name)
        if existing is not None:
            if not isinstance(existing, ir.Function):
                raise TypeError("FMA intrinsic symbol is not a function")
            return existing

        fn_ty = ir.FunctionType(ty, [ty, ty, ty])
        fn = ir.Function(self.module, fn_ty, name)
        fn.linkage = "external"
        return fn

    def emit_fma(
        self,
        lhs: ir.Value,
        rhs: ir.Value,
        addend: ir.Value,
    ) -> ir.Value:
        """
        title: Emit fma.
        parameters:
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value
          addend:
            type: ir.Value
        returns:
          type: ir.Value
        """
        builder = self.builder()
        if not isinstance(lhs.type, ir.VectorType) and hasattr(builder, "fma"):
            inst = builder.fma(lhs, rhs, addend, name="vfma")
            self.apply_fast_math(inst)
            return inst
        fma_fn = self.get_fma_function(lhs.type)
        inst = builder.call(fma_fn, [lhs, rhs, addend], name="vfma")
        self.apply_fast_math(inst)
        return inst

    def set_fast_math(self, enabled: bool) -> None:
        """
        title: Set fast math.
        parameters:
          enabled:
            type: bool
        """
        self.enabled = enabled

    def apply_fast_math(self, inst: ir.Instruction) -> None:
        """
        title: Apply fast math.
        parameters:
          inst:
            type: ir.Instruction
        """
        if not self.enabled:
            return

        type_ = inst.type
        if isinstance(type_, ir.VectorType):
            if not is_fp_type(type_.element):
                return
        elif not is_fp_type(type_):
            return

        flags = getattr(inst, "flags", None)
        if flags is None or "fast" in flags:
            return

        try:
            flags.append("fast")
        except (AttributeError, TypeError):
            return
