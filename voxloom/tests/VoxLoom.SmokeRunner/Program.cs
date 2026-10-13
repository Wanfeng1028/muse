// 临时验证工具：vstest 的 testhost 在本 VM 上 IPC 连不通，
// 用反射直接执行全部 [Fact] 用例（跑的是真实测试代码与断言）。
using System.Reflection;
using Xunit;

var asm = Assembly.Load("VoxLoom.Core.Tests");
int pass = 0, fail = 0;
var failures = new List<string>();

foreach (var type in asm.GetTypes().Where(t => t.IsClass && !t.IsAbstract))
{
    var facts = type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
        .Where(m => m.GetCustomAttribute<FactAttribute>() != null)
        .ToList();
    if (facts.Count == 0) continue;
    foreach (var m in facts)
    {
        var name = $"{type.Name}.{m.Name}";
        try
        {
            var instance = Activator.CreateInstance(type)!;
            var ret = m.Invoke(instance, null);
            if (ret is Task t) t.GetAwaiter().GetResult();
            if (instance is IDisposable d) d.Dispose();
            pass++;
            Console.WriteLine($"PASS {name}");
        }
        catch (Exception ex)
        {
            fail++;
            var inner = ex is TargetInvocationException tie && tie.InnerException != null ? tie.InnerException : ex;
            failures.Add($"{name}: {inner.GetType().Name}: {inner.Message.Split('\n')[0]}");
            Console.WriteLine($"FAIL {name}: {inner.Message.Split('\n')[0]}");
        }
    }
}

Console.WriteLine($"---- {pass} passed, {fail} failed ----");
return fail == 0 ? 0 : 1;
