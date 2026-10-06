using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace Bombinha.App.Ui;

/// <summary>Fração (0..1) ⇄ porcentagem (0..100).</summary>
public sealed class PercentConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => System.Convert.ToDouble(value, culture) * 100.0;
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => System.Convert.ToDouble(value, culture) / 100.0;
}

/// <summary>Segundos ⇄ milissegundos.</summary>
public sealed class SecondsToMsConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => System.Convert.ToDouble(value, culture) * 1000.0;
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => System.Convert.ToDouble(value, culture) / 1000.0;
}

/// <summary>Liga RadioButtons a um enum: marcado quando o valor é igual ao parâmetro.</summary>
public sealed class EnumEqualsConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => Equals(value, parameter);

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is true ? parameter : Binding.DoNothing;
}

/// <summary>Visível quando o valor é igual ao parâmetro (troca de páginas).</summary>
public sealed class EnumVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        Equals(value, parameter) ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>Esconde textos nulos ou vazios.</summary>
public sealed class EmptyToCollapsedConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is null || (value is string s && s.Length == 0) ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>Lista de frases ⇄ texto com uma frase por linha.</summary>
public sealed class LinesConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is IEnumerable<string> lines ? string.Join(Environment.NewLine, lines) : "";

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        ((value as string) ?? "").Split('\n').Select(l => l.TrimEnd('\r')).ToList();
}

/// <summary>Caminho opcional: nulo aparece como vazio (o campo mostra "embutido" como dica).</summary>
public sealed class OptionalPathConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => value as string ?? "";

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        string.IsNullOrWhiteSpace(value as string) ? null! : ((string)value).Trim();
}

public sealed class InverseBoolConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => value is not true;
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => value is not true;
}
