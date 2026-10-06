using Bombinha.Core.Settings;

namespace Bombinha.Core.Detection;

/// <summary>Responde "é a minha vez?" em três momentos diferentes da jogada.</summary>
public interface ITurnDetector
{
    /// <summary>Checagem do ciclo principal; renova a referência da barra de turno quando é a vez.</summary>
    bool DetectTurn(AppSettings settings);

    /// <summary>Checagem imediatamente antes do ENTER.</summary>
    bool ConfirmForSubmit(AppSettings settings);

    /// <summary>Checagem depois do ENTER: se ainda for a vez, a palavra foi recusada.</summary>
    bool IsStillMyTurn(AppSettings settings);

    /// <summary>Descarta a referência da barra (após recalibração).</summary>
    void ResetReference();
}
