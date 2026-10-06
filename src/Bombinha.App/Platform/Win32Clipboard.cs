using System.ComponentModel;
using System.Runtime.InteropServices;
using Bombinha.Core.Capture;

namespace Bombinha.App.Platform;

/// <summary>
/// Área de transferência via Win32, utilizável da thread do motor. O snapshot guarda todos os
/// formatos baseados em memória global (texto, HTML, imagens DIB, arquivos...), então copiar uma
/// imagem e iniciar o bot não a perde — a versão antiga só preservava texto e apagava o resto.
/// </summary>
internal sealed class Win32Clipboard(Func<nint> ownerWindow) : IClipboard
{
    private const long MaxSnapshotBytes = 64L * 1024 * 1024;
    // Outros programas (histórico do Windows, gerenciadores de clipboard) abrem a área de transferência
    // logo após cada cópia; esperamos até ~500 ms antes de desistir.
    private const int OpenAttempts = 25;
    private const int OpenRetryMs = 20;

    // Formatos que são handles GDI ou dependem do dono: não dá para copiar como bytes.
    private static readonly HashSet<uint> HandleFormats = [2 /*BITMAP*/, 3 /*METAFILEPICT*/, 9 /*PALETTE*/,
        14 /*ENHMETAFILE*/, 0x80 /*OWNERDISPLAY*/, 0x82 /*DSPBITMAP*/, 0x83 /*DSPMETAFILEPICT*/, 0x8E /*DSPENHMETAFILE*/];

    private static readonly uint ExcludeFromMonitoring = Native.RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing");
    private static readonly uint CanIncludeInHistory = Native.RegisterClipboardFormat("CanIncludeInClipboardHistory");

    private sealed record Snapshot(IReadOnlyList<(uint Format, byte[] Data)> Items) : IClipboardSnapshot;

    public uint SequenceNumber => Native.GetClipboardSequenceNumber();

    public string? TryGetText()
    {
        using var _ = Open(0);
        nint handle = Native.GetClipboardData(Native.CF_UNICODETEXT);
        if (handle == 0)
            return null;
        nint ptr = Native.GlobalLock(handle);
        if (ptr == 0)
            return null;
        try
        {
            return Marshal.PtrToStringUni(ptr);
        }
        finally
        {
            Native.GlobalUnlock(handle);
        }
    }

    public IClipboardSnapshot? TakeSnapshot()
    {
        using var _ = Open(0);
        var items = new List<(uint, byte[])>();
        long total = 0;
        uint format = 0;
        while ((format = Native.EnumClipboardFormats(format)) != 0)
        {
            if (HandleFormats.Contains(format))
                continue;
            nint handle = Native.GetClipboardData(format);
            if (handle == 0)
                continue;
            long size = (long)Native.GlobalSize(handle);
            if (size <= 0 || total + size > MaxSnapshotBytes)
                continue;
            nint ptr = Native.GlobalLock(handle);
            if (ptr == 0)
                continue;
            try
            {
                var data = new byte[size];
                Marshal.Copy(ptr, data, 0, data.Length);
                items.Add((format, data));
                total += size;
            }
            finally
            {
                Native.GlobalUnlock(handle);
            }
        }
        return items.Count == 0 ? null : new Snapshot(items);
    }

    public void Restore(IClipboardSnapshot snapshot)
    {
        var items = ((Snapshot)snapshot).Items;
        using var _ = Open(ownerWindow());
        if (!Native.EmptyClipboard())
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Falha ao limpar a área de transferência.");
        foreach (var (format, data) in items)
            Put(format, data);
        // Devolver o conteúdo do usuário não deve gerar uma entrada nova no histórico (Win+V).
        Put(CanIncludeInHistory, BitConverter.GetBytes(0));
        Put(ExcludeFromMonitoring, [0]);
    }

    private static void Put(uint format, byte[] data)
    {
        if (format == 0)
            return;
        nint mem = Native.GlobalAlloc(Native.GMEM_MOVEABLE, (nuint)Math.Max(1, data.Length));
        if (mem == 0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "GlobalAlloc falhou ao restaurar a área de transferência.");
        nint ptr = Native.GlobalLock(mem);
        Marshal.Copy(data, 0, ptr, data.Length);
        Native.GlobalUnlock(mem);
        if (Native.SetClipboardData(format, mem) == 0)
            Native.GlobalFree(mem); // em caso de sucesso, o Windows passa a ser o dono da memória
    }

    /// <summary>Abre a área de transferência, tentando de novo se outro programa a estiver usando.</summary>
    private static ClipboardScope Open(nint owner)
    {
        for (int attempt = 1; ; attempt++)
        {
            if (Native.OpenClipboard(owner))
                return new ClipboardScope();
            if (attempt >= OpenAttempts)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "A área de transferência está em uso por outro programa.");
            Thread.Sleep(OpenRetryMs);
        }
    }

    private readonly struct ClipboardScope : IDisposable
    {
        public void Dispose() => Native.CloseClipboard();
    }
}
