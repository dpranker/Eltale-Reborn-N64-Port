set pagination off
set confirm off
set width 0
set architecture mips:4300
set endian big
eval "target remote 127.0.0.1:%d", $port

set $failures = 0
define check
  if $arg0
    printf "ok: %s\n", $arg1
  else
    printf "FAIL: %s\n", $arg1
    set $failures = $failures + 1
  end
end
define finish_test
  detach
  if $failures
    quit 1
  end
  quit 0
end
