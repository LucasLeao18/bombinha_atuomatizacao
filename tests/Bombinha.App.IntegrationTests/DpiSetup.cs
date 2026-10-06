using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Bombinha.App.IntegrationTests;

/// <summary>O app declara PerMonitorV2 no manifesto; o host de testes precisa do mesmo modo.</summary>
internal static partial class DpiSetup
{
    private static readonly nint PerMonitorAwareV2 = -4;

    [ModuleInitializer]
    internal static void Initialize() => SetProcessDpiAwarenessContext(PerMonitorAwareV2);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool SetProcessDpiAwarenessContext(nint value);
}
