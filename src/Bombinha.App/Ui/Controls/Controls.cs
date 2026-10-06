using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;

namespace Bombinha.App.Ui.Controls;

/// <summary>Cartão com título e subtítulo opcionais (o visual fica em Theme.xaml).</summary>
public sealed class Card : HeaderedContentControl
{
    public static readonly DependencyProperty SubtitleProperty =
        DependencyProperty.Register(nameof(Subtitle), typeof(string), typeof(Card));

    public string? Subtitle
    {
        get => (string?)GetValue(SubtitleProperty);
        set => SetValue(SubtitleProperty, value);
    }
}

/// <summary>Linha de formulário: rótulo e dica à esquerda, controle à direita, alinhados entre linhas.</summary>
public sealed class SettingRow : ContentControl
{
    public static readonly DependencyProperty LabelProperty =
        DependencyProperty.Register(nameof(Label), typeof(string), typeof(SettingRow));

    public static readonly DependencyProperty HintProperty =
        DependencyProperty.Register(nameof(Hint), typeof(string), typeof(SettingRow));

    public string? Label
    {
        get => (string?)GetValue(LabelProperty);
        set => SetValue(LabelProperty, value);
    }

    public string? Hint
    {
        get => (string?)GetValue(HintProperty);
        set => SetValue(HintProperty, value);
    }
}

/// <summary>Número grande com legenda e faixa colorida.</summary>
public sealed class StatTile : Control
{
    public static readonly DependencyProperty CaptionProperty =
        DependencyProperty.Register(nameof(Caption), typeof(string), typeof(StatTile));

    public static readonly DependencyProperty ValueProperty =
        DependencyProperty.Register(nameof(Value), typeof(object), typeof(StatTile));

    public static readonly DependencyProperty AccentProperty =
        DependencyProperty.Register(nameof(Accent), typeof(Brush), typeof(StatTile));

    public string? Caption
    {
        get => (string?)GetValue(CaptionProperty);
        set => SetValue(CaptionProperty, value);
    }

    public object? Value
    {
        get => GetValue(ValueProperty);
        set => SetValue(ValueProperty, value);
    }

    public Brush? Accent
    {
        get => (Brush?)GetValue(AccentProperty);
        set => SetValue(AccentProperty, value);
    }
}

/// <summary>Slider com o valor formatado ao lado (casas decimais e sufixo configuráveis).</summary>
public sealed class SettingSlider : Control
{
    public static readonly DependencyProperty ValueProperty = DependencyProperty.Register(
        nameof(Value), typeof(double), typeof(SettingSlider),
        new FrameworkPropertyMetadata(0.0, FrameworkPropertyMetadataOptions.BindsTwoWayByDefault, OnDisplayInputsChanged));

    public static readonly DependencyProperty MinimumProperty =
        DependencyProperty.Register(nameof(Minimum), typeof(double), typeof(SettingSlider), new PropertyMetadata(0.0));

    public static readonly DependencyProperty MaximumProperty =
        DependencyProperty.Register(nameof(Maximum), typeof(double), typeof(SettingSlider), new PropertyMetadata(100.0));

    public static readonly DependencyProperty DecimalsProperty = DependencyProperty.Register(
        nameof(Decimals), typeof(int), typeof(SettingSlider), new PropertyMetadata(0, OnDisplayInputsChanged));

    public static readonly DependencyProperty SuffixProperty = DependencyProperty.Register(
        nameof(Suffix), typeof(string), typeof(SettingSlider), new PropertyMetadata("", OnDisplayInputsChanged));

    private static readonly DependencyPropertyKey DisplayKey = DependencyProperty.RegisterReadOnly(
        nameof(Display), typeof(string), typeof(SettingSlider), new PropertyMetadata("0"));

    public static readonly DependencyProperty DisplayProperty = DisplayKey.DependencyProperty;

    private static readonly DependencyPropertyKey StepKey = DependencyProperty.RegisterReadOnly(
        nameof(Step), typeof(double), typeof(SettingSlider), new PropertyMetadata(1.0));

    public static readonly DependencyProperty StepProperty = StepKey.DependencyProperty;

    public double Value
    {
        get => (double)GetValue(ValueProperty);
        set => SetValue(ValueProperty, value);
    }

    public double Minimum
    {
        get => (double)GetValue(MinimumProperty);
        set => SetValue(MinimumProperty, value);
    }

    public double Maximum
    {
        get => (double)GetValue(MaximumProperty);
        set => SetValue(MaximumProperty, value);
    }

    public int Decimals
    {
        get => (int)GetValue(DecimalsProperty);
        set => SetValue(DecimalsProperty, value);
    }

    public string Suffix
    {
        get => (string)GetValue(SuffixProperty);
        set => SetValue(SuffixProperty, value);
    }

    public string Display => (string)GetValue(DisplayProperty);

    /// <summary>Passo do slider: 1 para inteiros, 0.01 para 2 casas etc.</summary>
    public double Step => (double)GetValue(StepProperty);

    private static void OnDisplayInputsChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        var s = (SettingSlider)d;
        int decimals = Math.Clamp(s.Decimals, 0, 4);
        s.SetValue(StepKey, Math.Pow(10, -decimals));
        string number = s.Value.ToString("F" + decimals, CultureInfo.CurrentCulture);
        s.SetValue(DisplayKey, string.IsNullOrEmpty(s.Suffix) ? number : $"{number} {s.Suffix}");
    }
}

/// <summary>Campo inteiro com botões − e +.</summary>
[TemplatePart(Name = "PART_Down", Type = typeof(ButtonBase))]
[TemplatePart(Name = "PART_Up", Type = typeof(ButtonBase))]
public sealed class NumericStepper : Control
{
    public static readonly DependencyProperty ValueProperty = DependencyProperty.Register(
        nameof(Value), typeof(int), typeof(NumericStepper),
        new FrameworkPropertyMetadata(0, FrameworkPropertyMetadataOptions.BindsTwoWayByDefault, null,
            (d, value) => Math.Clamp((int)value, ((NumericStepper)d).Minimum, Math.Max(((NumericStepper)d).Minimum, ((NumericStepper)d).Maximum))));

    public static readonly DependencyProperty MinimumProperty =
        DependencyProperty.Register(nameof(Minimum), typeof(int), typeof(NumericStepper), new PropertyMetadata(0));

    public static readonly DependencyProperty MaximumProperty =
        DependencyProperty.Register(nameof(Maximum), typeof(int), typeof(NumericStepper), new PropertyMetadata(100));

    private ButtonBase? _down;
    private ButtonBase? _up;

    public int Value
    {
        get => (int)GetValue(ValueProperty);
        set => SetValue(ValueProperty, value);
    }

    public int Minimum
    {
        get => (int)GetValue(MinimumProperty);
        set => SetValue(MinimumProperty, value);
    }

    public int Maximum
    {
        get => (int)GetValue(MaximumProperty);
        set => SetValue(MaximumProperty, value);
    }

    public override void OnApplyTemplate()
    {
        if (_down is not null)
            _down.Click -= OnDown;
        if (_up is not null)
            _up.Click -= OnUp;
        base.OnApplyTemplate();
        _down = GetTemplateChild("PART_Down") as ButtonBase;
        _up = GetTemplateChild("PART_Up") as ButtonBase;
        if (_down is not null)
            _down.Click += OnDown;
        if (_up is not null)
            _up.Click += OnUp;
    }

    private void OnDown(object sender, RoutedEventArgs e) => Value = Math.Max(Minimum, Value - 1);

    private void OnUp(object sender, RoutedEventArgs e) => Value = Math.Min(Maximum, Value + 1);
}

/// <summary>Propriedades anexadas usadas pelos estilos (cor de hover, ícone, descrição).</summary>
public static class UiProps
{
    public static readonly DependencyProperty HoverProperty =
        DependencyProperty.RegisterAttached("Hover", typeof(Brush), typeof(UiProps));

    public static readonly DependencyProperty IconProperty =
        DependencyProperty.RegisterAttached("Icon", typeof(string), typeof(UiProps));

    public static readonly DependencyProperty DescriptionProperty =
        DependencyProperty.RegisterAttached("Description", typeof(string), typeof(UiProps));

    public static Brush? GetHover(DependencyObject o) => (Brush?)o.GetValue(HoverProperty);
    public static void SetHover(DependencyObject o, Brush? value) => o.SetValue(HoverProperty, value);

    public static string? GetIcon(DependencyObject o) => (string?)o.GetValue(IconProperty);
    public static void SetIcon(DependencyObject o, string? value) => o.SetValue(IconProperty, value);

    public static string? GetDescription(DependencyObject o) => (string?)o.GetValue(DescriptionProperty);
    public static void SetDescription(DependencyObject o, string? value) => o.SetValue(DescriptionProperty, value);
}
