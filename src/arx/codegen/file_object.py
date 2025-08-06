"""File Object, Executable or LLVM IR generation."""

import logging
import os
import sys

from typing import Any, Dict, List, Union

from llvmlite import binding as llvm
from llvmlite import ir

from arx import ast
from arx.codegen.base import CodeGenLLVMBase
from arx.io import ArxFile, ArxIO
from arx.lexer import Lexer
from arx.parser import Parser

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


INPUT_FILE: str = ""
OUTPUT_FILE: str = ""
ARX_VERSION: str = ""
IS_BUILD_LIB: bool = True


class ObjectGenerator(CodeGenLLVMBase):
    """Generate object files or executable from an AST."""

    function_protos: Dict[str, ast.PrototypeAST]
    output_file: str = ""
    input_file: str = ""
    is_lib: bool = True
    result_stack: List[Union[ir.Value, ir.Function]] = []

    def __init__(
        self,
        input_file: str = "",
        output_file: str = "tmp.o",
        is_lib: bool = True,
    ):
        self.input_file = input_file
        self.output_file = output_file or f"{input_file}.o"
        self.is_lib = is_lib

        self.function_protos: Dict[str, ast.PrototypeAST] = {}
        self.module = ir.Module()

        self.result_stack: List[Union[ir.Value, ir.Function]] = []

        super().initialize()

        logging.info("target_triple")
        self.target = llvm.Target.from_default_triple()
        self.target_machine = self.target.create_target_machine(
            codemodel="small"
        )

        self._add_builtins()

    def _add_builtins(self) -> None:
        # The C++ tutorial adds putchard() simply by defining it in the host
        # C++ code, which is then accessible to the JIT. It doesn't work as
        # simply for us; but luckily it's very easy to define new "C level"
        # functions for our JITed code to use - just emit them as LLVM IR.
        # This is what this method does.

        # Add the declaration of putchar
        putchar_ty = ir.FunctionType(
            self._llvm.INT32_TYPE, [self._llvm.INT32_TYPE]
        )
        putchar = ir.Function(self._llvm.module, putchar_ty, "putchar")

        # Add putchard
        putchard_ty = ir.FunctionType(
            self._llvm.FLOAT_TYPE, [self._llvm.FLOAT_TYPE]
        )
        putchard = ir.Function(self._llvm.module, putchard_ty, "putchard")

        ir_builder = ir.IRBuilder(putchard.append_basic_block("entry"))

        ival = ir_builder.fptoui(
            putchard.args[0], self._llvm.INT32_TYPE, "intcast"
        )

        ir_builder.call(putchar, [ival])
        ir_builder.ret(ir.Constant(self._llvm.FLOAT_TYPE, 0))

    def evaluate(
        self, block_ast: ast.BlockAST, show_llvm_ir: bool = False
    ) -> None:
        """
        Compile an AST to an object file.

        Parameters
        ----------
            block_ast: The AST tree object.

        Returns
        -------
            int: The compilation result.
        """
        logging.info("Starting main_loop")
        self.emit_object(block_ast)

        # Convert LLVM IR into in-memory representation
        if show_llvm_ir:
            return print(str(self._llvm.module))

        result_mod = llvm.parse_assembly(str(self._llvm.module))
        result_object = self.target_machine.emit_object(result_mod)

        if self.output_file == "":
            self.output_file = self.input_file + ".o"

        # Output object code to a file.
        with open(self.output_file, "wb") as obj_file:
            obj_file.write(result_object)
            print("Wrote " + self.output_file)

        if not self.is_lib:
            self.compile_executable()

    def compile_executable(self) -> None:
        """Compile into an executable file."""
        print("Not fully implemented yet.")
        # generate an executable file

        linker_path = "clang++"
        executable_path = self.input_file + "c"
        # note: it just has a purpose to demonstrate an initial implementation
        #       it will be improved in a follow-up PR
        content = (
            "#include <iostream>\n"
            "int main() {\n"
            '  std::cout << "ARX[WARNING]: '
            'This is an empty executable file" << std::endl;\n'
            "}\n"
        )

        main_cpp_path = ArxFile.create_tmp_file(content)

        if main_cpp_path == "":
            raise Exception("ARX[FAIL]: Executable file was not created.")

        # Example (running it from a shell prompt):
        # clang++ \
        #   ${CLANG_EXTRAS} \
        #   ${DEBUG_FLAGS} \
        #   -fPIC \
        #   -std=c++20 \
        #   "${TEST_DIR_PATH}/integration/${test_name}.cpp" \
        #   ${OBJECT_FILE} \
        #   -o "${TMP_DIR}/main"

        compiler_args = [
            "-fPIC",
            "-std=c++20",
            main_cpp_path,
            self.output_file,
            "-o",
            executable_path,
        ]

        # Add any additional compiler flags or include paths as needed
        # compiler_args.append("-I/path/to/include")

        linker_path = "clang++"
        compiler_cmd = linker_path + " " + " ".join(compiler_args)

        print("ARX[INFO]: ", compiler_cmd)
        compile_result = os.system(compiler_cmd)  # nosec

        ArxFile.delete_file(main_cpp_path)

        if compile_result != 0:
            llvm.errs() << "failed to compile and link object file"
            sys.exit(1)

    def open_interactive(self) -> None:
        """
        Open the Arx shell.

        Returns
        -------
            int: The compilation result.
        """
        # Prime the first token.
        print(f"Arx {ARX_VERSION} \n")
        print(">>> ")

        lexer = Lexer()
        parser = Parser()

        while True:
            try:
                ArxIO.string_to_buffer(input())
                self.evaluate(parser.parse(lexer.lex()))
            except KeyboardInterrupt:
                break

    def get_function(self, name: str) -> ir.Function:
        """
        Put the function defined by the given name to result_func.

        Parameters
        ----------
            name: Function name
        """
        if name in self._llvm.module.globals:
            fn = self._llvm.module.get_global(name)
            self.result_stack.append(fn)
            return

        if name in self.function_protos:
            self.visit(self.function_protos[name])
            return

    def create_entry_block_alloca(
        self, var_name: str, type_name: str
    ) -> Any:  # llvm.AllocaInst
        """
        Create an alloca instruction in the entry block of the function.

        This is used for mutable variables, etc.

        Parameters
        ----------
        fn: The llvm function
        var_name: The variable name
        type_name: The type name

        Returns
        -------
          An llvm allocation instance.
        """
        tmp_builder = ir.IRBuilder()
        tmp_builder.position_at_start(
            self._llvm.ir_builder.function.entry_basic_block
        )
        return tmp_builder.alloca(
            self._llvm.get_data_type(type_name), None, var_name
        )

    def emit_object(self, tree: ast.BlockAST) -> None:
        """
        Walk the AST and generate code for each node.

        top ::= definition | external | expression | ';'

        Parameters
        ----------
            tree: The ast.BlockAST instance.
        """
        self.visit_block(tree)

    def visit_float_expr(self, expr: ast.FloatExprAST) -> None:
        """
        Code generation for ast.FloatExprAST.

        Parameters
        ----------
            expr: The ast.FloatExprAST instance
        """
        result = ir.Constant(self._llvm.FLOAT_TYPE, expr.value)
        self.result_stack.append(result)

    def visit_variable_expr(self, expr: ast.VariableExprAST) -> None:
        """
        Code generation for ast.VariableExprAST.

        Parameters
        ----------
            expr: The ast.VariableExprAST instance
        """
        expr_var = self.named_values.get(expr.name)

        if not expr_var:
            msg = f"Unknown variable name: {expr.name}"
            raise Exception(msg)

        result = self._llvm.ir_builder.load(expr_var, expr.name)
        self.result_stack.append(result)

    def visit_unary_expr(self, expr: ast.UnaryExprAST) -> None:
        """
        Code generation for ast.UnaryExprAST.

        Parameters
        ----------
            expr: The ast.UnaryExprAST instance
        """
        self.visit(expr.operand)
        operand_value = self.result_stack.pop()
        if not operand_value:
            raise Exception("ObjectGen: Empty unary operand.")

        fn = self.get_function("unary" + expr.op_code)
        if not fn:
            raise Exception("Unknown unary operator")

        result = self._llvm.ir_builder.call(fn, [operand_value], "unop")
        self.result_stack.append(result)

    def visit_binary_expr(self, expr: ast.BinaryExprAST) -> None:
        """
        Code generation for ast.BinaryExprAST.

        Parameters
        ----------
            expr: The ast.BinaryExprAST instance
        """
        if expr.op == "=":
            # Special case '=' because we don't want to emit the lhs as an
            # expression.
            # Assignment requires the lhs to be an identifier.
            # This assumes we're building without RTTI because LLVM builds
            # that way by default.
            # If you build LLVM with RTTI, this can be changed to a
            # dynamic_cast for automatic error checking.
            var_lhs = expr.lhs

            if not isinstance(var_lhs, ast.VariableExprAST):
                raise Exception("destination of '=' must be a variable")

            # Codegen the rhs.
            self.visit(expr.rhs)
            llvm_rhs = self.result_stack.pop()

            if not llvm_rhs:
                raise Exception("codegen: Invalid rhs expression.")

            # Look up the name.
            llvm_lhs = self.named_values[var_lhs.get_name()]

            if not llvm_lhs:
                raise Exception("codegen: Invalid lhs variable name")

            self._llvm.ir_builder.store(llvm_rhs, llvm_lhs)
            result = llvm_rhs
            self.result_stack.append(result)
            return

        self.visit(expr.lhs)
        llvm_lhs = self.result_stack.pop()
        self.visit(expr.rhs)
        llvm_rhs = self.result_stack.pop()

        if not llvm_lhs or not llvm_rhs:
            raise Exception("codegen: Invalid lhs/rhs")

        if expr.op == "+":
            result = self._llvm.ir_builder.fadd(llvm_lhs, llvm_rhs, "addtmp")
            self.result_stack.append(result)
            return
        elif expr.op == "-":
            result = self._llvm.ir_builder.fsub(llvm_lhs, llvm_rhs, "subtmp")
            self.result_stack.append(result)
            return
        elif expr.op == "*":
            result = self._llvm.ir_builder.fmul(llvm_lhs, llvm_rhs, "multmp")
            self.result_stack.append(result)
            return
        elif expr.op == "<":
            cmp_result = self._llvm.ir_builder.fcmp_unordered(
                "<", llvm_lhs, llvm_rhs, "lttmp"
            )
            # Convert bool 0/1 to float 0.0 or 1.0
            result = self._llvm.ir_builder.uitofp(
                cmp_result, self._llvm.FLOAT_TYPE, "booltmp"
            )
            self.result_stack.append(result)
            return
        elif expr.op == ">":
            cmp_result = self._llvm.ir_builder.fcmp_unordered(
                ">", llvm_lhs, llvm_rhs, "gttmp"
            )
            # Convert bool 0/1 to float 0.0 or 1.0
            result = self._llvm.ir_builder.uitofp(
                cmp_result, self._llvm.FLOAT_TYPE, "booltmp"
            )
            self.result_stack.append(result)
            return

        # If it wasn't a builtin binary operator, it must be a user defined
        # one. Emit a call to it.
        fn = self.get_function("binary" + expr.op)
        result = self._llvm.ir_builder.call(fn, [llvm_lhs, llvm_rhs], "binop")
        self.result_stack.append(result)

    def visit_block(self, expr: ast.BlockAST) -> None:
        """Visit method for BlockAST."""
        result = []
        for node in expr.nodes:
            self.visit(node)
            result.append(self.result_stack.pop())
        self.result_stack.append(result)

    def visit_call_expr(self, expr: ast.CallExprAST) -> None:
        """
        Code generation for ast.CallExprAST.

        Parameters
        ----------
            expr: The ast.CallExprAST instance
        """
        callee_f = self.get_function(expr.callee)

        if not callee_f:
            raise Exception("Unknown function referenced")

        if len(callee_f.args) != len(expr.args):
            raise Exception("codegen: Incorrect # arguments passed.")

        llvm_args = []
        for arg in expr.args:
            self.visit(arg)
            llvm_arg = self.result_stack.pop()
            if not llvm_arg:
                raise Exception("codegen: Invalid callee argument.")
            llvm_args.append(llvm_arg)

        result = self._llvm.ir_builder.call(callee_f, llvm_args, "calltmp")
        self.result_stack.append(result)

    def visit_if_stmt(self, expr: ast.IfStmtAST) -> None:
        """
        Code generation for ast.IfStmtAST.

        Parameters
        ----------
            expr: The ast.IfStmtAST instance
        """
        self.visit(expr.cond)
        cond_v = self.result_stack.pop()

        if not cond_v:
            raise Exception("codegen: Invalid condition expression.")

        # Convert condition to a bool by comparing non-equal to 0.0.
        cond_v = self._llvm.ir_builder.fcmp_ordered(
            "!=",
            cond_v,
            ir.Constant(self._llvm.FLOAT_TYPE, 0.0),
        )

        # fn = self._llvm.ir_builder.position_at_start().getParent()

        # Create blocks for the then and else cases. Insert the 'then' block
        # at the end of the function.
        # then_bb = ir.Block(self._llvm.ir_builder.function, "then", fn)
        then_bb = self._llvm.ir_builder.function.append_basic_block("then")
        else_bb = ir.Block(self._llvm.ir_builder.function, "else")
        merge_bb = ir.Block(self._llvm.ir_builder.function, "ifcont")

        self._llvm.ir_builder.cbranch(cond_v, then_bb, else_bb)

        # Emit then value.
        self._llvm.ir_builder.position_at_start(then_bb)
        self.visit(expr.then_)
        then_v = self.result_stack.pop()

        if not then_v:
            raise Exception("codegen: `Then` expression is invalid.")

        self._llvm.ir_builder.branch(merge_bb)

        # Codegen of 'then' can change the current block, update then_bb
        # for the PHI.
        then_bb = self._llvm.ir_builder.block

        # Emit else block.
        self._llvm.ir_builder.function.basic_blocks.append(else_bb)
        self._llvm.ir_builder.position_at_start(else_bb)
        self.visit(expr.else_)
        else_v = self.result_stack.pop()
        if not else_v:
            raise Exception("Revisit this!")

        # Emission of else_val could have modified the current basic block.
        else_bb = self._llvm.ir_builder.block
        self._llvm.ir_builder.branch(merge_bb)

        # Emit merge block.
        self._llvm.ir_builder.function.basic_blocks.append(merge_bb)
        self._llvm.ir_builder.position_at_start(merge_bb)
        phi = self._llvm.ir_builder.phi(self._llvm.FLOAT_TYPE, "iftmp")

        phi.add_incoming(then_v, then_bb)
        phi.add_incoming(else_v, else_bb)

        self.result_stack.append(phi)

    def visit_for_stmt(self, expr: ast.ForStmtAST) -> None:
        """
        Code generation for ast.ForStmtAST.

        Parameters
        ----------
            expr: The ast.ForStmtAST instance.
        """
        saved_block = self._llvm.ir_builder.block
        var_addr = self.create_entry_block_alloca(expr.var_name, "float")
        self._llvm.ir_builder.position_at_end(saved_block)

        # Emit the start code first, without 'variable' in scope.
        self.visit(expr.start)
        start_val = self.result_stack.pop()
        if not start_val:
            raise Exception("codegen: Invalid start argument.")

        # Store the value into the alloca.
        self._llvm.ir_builder.store(start_val, var_addr)

        # Make the new basic block for the loop header, inserting after
        # current block.
        loop_bb = self._llvm.ir_builder.function.append_basic_block("loop")

        # Insert an explicit fall through from the current block to the
        # loop_bb.
        self._llvm.ir_builder.branch(loop_bb)

        # Start insertion in loop_bb.
        self._llvm.ir_builder.position_at_start(loop_bb)

        # Within the loop, the variable is defined equal to the PHI node.
        # If it shadows an existing variable, we have to restore it, so save
        # it now.
        old_val = self.named_values.get(expr.var_name)
        self.named_values[expr.var_name] = var_addr

        # Emit the body of the loop. This, like any other expr, can change
        # the current basic_block. Note that we ignore the value computed by
        # the body, but don't allow an error.
        self.visit(expr.body)
        body_val = self.result_stack.pop()

        if not body_val:
            return

        # Emit the step value.
        if expr.step:
            self.visit(expr.step)
            step_val = self.result_stack.pop()
            if not step_val:
                return
        else:
            # If not specified, use 1.0.
            step_val = ir.Constant(self._llvm.FLOAT_TYPE, 1.0)

        # Compute the end condition.
        self.visit(expr.end)
        end_cond = self.result_stack.pop()
        if not end_cond:
            return

        # Reload, increment, and restore the var_addr. This handles the case
        # where the body of the loop mutates the variable.
        cur_var = self._llvm.ir_builder.load(var_addr, expr.var_name)
        next_var = self._llvm.ir_builder.fadd(cur_var, step_val, "nextvar")
        self._llvm.ir_builder.store(next_var, var_addr)

        # Convert condition to a bool by comparing non-equal to 0.0.
        end_cond = self._llvm.ir_builder.fcmp_ordered(
            "!=",
            end_cond,
            ir.Constant(self._llvm.DOUBLE_TYPE, 0.0),
            "loopcond",
        )

        # Create the "after loop" block and insert it.
        after_bb = self._llvm.ir_builder.function.append_basic_block(
            "afterloop"
        )

        # Insert the conditional branch into the end of loop_bb.
        self._llvm.ir_builder.cbranch(end_cond, loop_bb, after_bb)

        # Any new code will be inserted in after_bb.
        self._llvm.ir_builder.position_at_start(after_bb)

        # Restore the unshadowed variable.
        if old_val:
            self.named_values[expr.var_name] = old_val
        else:
            self.named_values.pop(expr.var_name, None)

        # for expr always returns 0.0.
        result = ir.Constant(self._llvm.FLOAT_TYPE, 0.0)
        self.result_stack.append(result)

    def visit_var_expr(self, expr: ast.VarExprAST) -> None:
        """
        Code generation for ast.VarExprAST.

        Parameters
        ----------
            expr: The ast.VarExprAST instance.
        """
        raise Exception(f"CodeGen for {expr} not implemented yet.")

    def visit_prototype(self, expr: ast.PrototypeAST) -> ir.Function:
        """
        Code generation for PrototypeExprAST.

        Parameters
        ----------
            expr: The ast.PrototypeAST instance.
        """
        args_type = [self._llvm.FLOAT_TYPE] * len(expr.args)
        return_type = self._llvm.get_data_type("float")
        fn_type = ir.FunctionType(return_type, args_type, False)

        fn = ir.Function(self._llvm.module, fn_type, expr.name)

        # Set names for all arguments.
        for idx, arg in enumerate(fn.args):
            fn.args[idx].name = expr.args[idx].name

        return fn

    def visit_function(self, expr: ast.FunctionAST) -> ir.Function:
        """
        Code generation for FunctionExprAST.

        Transfer ownership of the prototype to the ArxLLVM::function_protos
        map, but keep a reference to it for use below.

        Parameters
        ----------
            expr: The ast.FunctionAST instance.
        """
        proto = expr.proto
        self.function_protos[expr.proto.get_name()] = expr.proto
        fn = self.get_function(proto.get_name())

        if not fn:
            raise Exception("codegen: Invalid function.")

        # Create a new basic block to start insertion into.
        basic_block = fn.append_basic_block("entry")
        self._llvm.ir_builder = ir.IRBuilder(basic_block)

        for llvm_arg in fn.args:
            # Create an alloca for this variable.
            alloca = self._llvm.ir_builder.alloca(
                self._llvm.FLOAT_TYPE, name=llvm_arg.name
            )

            # Store the initial value into the alloca.
            self._llvm.ir_builder.store(llvm_arg, alloca)

            # Add arguments to variable symbol table.
            self.named_values[llvm_arg.name] = alloca

        self.visit(expr.body)
        retval = self.result_stack.pop()

        # Validate the generated code, checking for consistency.
        if retval:
            self._llvm.ir_builder.ret(retval)
        else:
            self._llvm.ir_builder.ret(ir.Constant(self._llvm.FLOAT_TYPE, 0))
        return fn

    def visit_return_stmt(self, expr: ast.ReturnStmtAST) -> None:
        """
        Code generation for ast.ReturnStmtAST.

        Parameters
        ----------
            expr: The ast.ReturnStmtAST instance.
        """
        # llvm_return_val = self.result_val
        #
        # if llvm_return_val:
        #     self._llvm.ir_builder.CreateRet(llvm_return_val)
        return
