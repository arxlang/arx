; Unboxed f64 reference, not Arx frontend throughput or a nullable backend.
; No fast-math, reassociation, reduction, or Arrow dependency.
define void @add_f64(ptr %input, ptr %output, i64 %length, double %rhs) {
entry:
  %empty = icmp eq i64 %length, 0
  br i1 %empty, label %exit, label %loop
loop:
  %index = phi i64 [0, %entry], [%next, %loop]
  %source = getelementptr double, ptr %input, i64 %index
  %value = load double, ptr %source
  %sum = fadd double %value, %rhs
  %target = getelementptr double, ptr %output, i64 %index
  store double %sum, ptr %target
  %next = add i64 %index, 1
  %finished = icmp eq i64 %next, %length
  br i1 %finished, label %exit, label %loop
exit:
  ret void
}
