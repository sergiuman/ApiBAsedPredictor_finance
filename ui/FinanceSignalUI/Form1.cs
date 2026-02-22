using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinanceSignalUI;

public class Form1 : Form
{
    // -----------------------------------------------------------------------
    // Settings model
    // -----------------------------------------------------------------------

    private sealed class AppSettings
    {
        [JsonPropertyName("historyFilePath")]  public string HistoryFilePath  { get; set; } = "";
        [JsonPropertyName("pythonExe")]        public string PythonExe        { get; set; } = "python";
        [JsonPropertyName("projectDir")]       public string ProjectDir       { get; set; } = "";
        [JsonPropertyName("tickers")]          public List<string> Tickers    { get; set; } = new();
        [JsonPropertyName("aiProvider")]       public string AiProvider       { get; set; } = "openai";
        [JsonPropertyName("openaiKey")]        public string OpenAiKey        { get; set; } = "";
        [JsonPropertyName("openaiModel")]      public string OpenAiModel      { get; set; } = "gpt-4o-mini";
        [JsonPropertyName("claudeKey")]        public string ClaudeKey        { get; set; } = "";
        [JsonPropertyName("claudeModel")]      public string ClaudeModel      { get; set; } = "claude-opus-4-6";
        [JsonPropertyName("googleKey")]        public string GoogleKey        { get; set; } = "";
        [JsonPropertyName("googleModel")]      public string GoogleModel      { get; set; } = "gemini-1.5-flash";
        [JsonPropertyName("perplexityKey")]    public string PerplexityKey    { get; set; } = "";
        [JsonPropertyName("perplexityModel")]  public string PerplexityModel  { get; set; } = "sonar";
        [JsonPropertyName("confidenceThreshold")] public int ConfidenceThreshold { get; set; } = 40;
    }

    private AppSettings _settings = new();
    private readonly string _settingsPath =
        Path.Combine(AppContext.BaseDirectory, "settings.json");

    // -----------------------------------------------------------------------
    // Control fields
    // -----------------------------------------------------------------------

    // Settings panel
    private Panel       _settingsPanel  = null!;
    private TextBox     _historyFileBox = null!;
    private TextBox     _pythonExeBox   = null!;
    private TextBox     _projectDirBox  = null!;
    private Button      _settingsToggle = null!;

    // Ticker list
    private CheckedListBox _tickerList = null!;

    // AI provider
    private RadioButton _radioOpenAI     = null!;
    private RadioButton _radioClaude     = null!;
    private RadioButton _radioGoogle     = null!;
    private RadioButton _radioPerplexity = null!;

    private TextBox _openaiKeyBox     = null!;
    private TextBox _claudeKeyBox     = null!;
    private TextBox _googleKeyBox     = null!;
    private TextBox _perplexityKeyBox = null!;

    private TextBox _openaiModelBox     = null!;
    private TextBox _claudeModelBox     = null!;
    private TextBox _googleModelBox     = null!;
    private TextBox _perplexityModelBox = null!;

    private NumericUpDown _confidenceNum = null!;
    private Button        _runBtn        = null!;
    private ProgressBar   _progressBar   = null!;
    private Label         _progressLabel = null!;

    // Results
    private DataGridView _resultsGrid = null!;
    private RichTextBox  _reportBox   = null!;
    private ToolStripStatusLabel _statusLabel = null!;

    // State
    private readonly Dictionary<string, string> _reportCache = new(StringComparer.OrdinalIgnoreCase);
    private CancellationTokenSource? _cts;
    private bool _loading; // suppress event-driven saves during LoadSettings

    // History tab
    private TabControl     _mainTabControl      = null!;
    private DataGridView   _historyGrid         = null!;
    private ComboBox       _historyTickerFilter = null!;
    private DateTimePicker _historyFromDate     = null!;
    private DateTimePicker _historyToDate       = null!;
    private Label          _historySummaryLabel = null!;
    private int            _historySortCol      = 0;
    private SortOrder      _historySortOrder    = SortOrder.Descending;

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    public Form1()
    {
        Text            = "Finance Signal Pro";
        Width           = 1380;
        Height          = 900;
        MinimumSize     = new Size(1050, 720);
        StartPosition   = FormStartPosition.CenterScreen;
        BackColor       = Color.FromArgb(240, 242, 246);

        BuildLayout();
        LoadSettings();

        if (string.IsNullOrEmpty(_settings.HistoryFilePath))
            AutoDetectHistoryFile();

        Load += (_, _) => LoadHistoryFromFile(); // populate history tab after handle is created
    }

    // -----------------------------------------------------------------------
    // Layout construction
    // -----------------------------------------------------------------------

    private void BuildLayout()
    {
        SuspendLayout();

        // ── Status strip ────────────────────────────────────────────────────
        var statusStrip = new StatusStrip
        {
            Dock      = DockStyle.Bottom,
            BackColor = Color.FromArgb(30, 36, 48),
            ForeColor = Color.LightGray,
            SizingGrip = false,
        };
        _statusLabel = new ToolStripStatusLabel("Ready")
        {
            Spring    = true,
            TextAlign = ContentAlignment.MiddleLeft,
            ForeColor = Color.FromArgb(170, 190, 220),
        };
        statusStrip.Items.Add(_statusLabel);

        // ── Top bar ─────────────────────────────────────────────────────────
        var topBar = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 40,
            BackColor = Color.FromArgb(22, 28, 42),
        };
        var titleLabel = new Label
        {
            Text      = "FINANCE SIGNAL PRO",
            ForeColor = Color.FromArgb(90, 175, 255),
            Font      = new Font("Segoe UI", 11.5f, FontStyle.Bold),
            AutoSize  = true,
            Location  = new Point(14, 9),
        };
        _settingsToggle = new Button
        {
            Text      = "⚙  Settings",
            ForeColor = Color.FromArgb(180, 190, 210),
            BackColor = Color.FromArgb(40, 50, 70),
            FlatStyle = FlatStyle.Flat,
            Location  = new Point(232, 7),
            Width     = 100,
            Height    = 26,
            Cursor    = Cursors.Hand,
            Font      = new Font("Segoe UI", 9f),
        };
        _settingsToggle.FlatAppearance.BorderColor = Color.FromArgb(60, 75, 100);
        _settingsToggle.Click += ToggleSettings;
        topBar.Controls.AddRange(new Control[] { titleLabel, _settingsToggle });

        // ── Settings panel (initially collapsed) ────────────────────────────
        _settingsPanel = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 110,
            BackColor = Color.FromArgb(248, 249, 252),
            Visible   = false,
        };
        BuildSettingsContent(_settingsPanel);

        // ── Main content area ────────────────────────────────────────────────
        var contentPanel = new Panel { Dock = DockStyle.Fill };

        // Left: Ticker list (fixed width)
        var leftPanel = new Panel
        {
            Dock      = DockStyle.Left,
            Width     = 260,
            BackColor = Color.White,
            Padding   = new Padding(0),
        };
        BuildTickerPanel(leftPanel);

        // Left separator line
        var separator = new Panel
        {
            Dock      = DockStyle.Left,
            Width     = 1,
            BackColor = Color.FromArgb(210, 215, 228),
        };

        // Right: AI config + results
        var rightPanel = new Panel { Dock = DockStyle.Fill };
        BuildRightPanel(rightPanel);

        contentPanel.Controls.Add(rightPanel);
        contentPanel.Controls.Add(separator);
        contentPanel.Controls.Add(leftPanel);

        // Assemble form (reverse z-order: last added = topmost z = processed first)
        Controls.Add(contentPanel);
        Controls.Add(_settingsPanel);
        Controls.Add(topBar);
        Controls.Add(statusStrip);

        ResumeLayout(false);
        PerformLayout();
    }

    private void BuildSettingsContent(Panel parent)
    {
        var tbl = new TableLayoutPanel
        {
            Dock        = DockStyle.Fill,
            ColumnCount = 3,
            RowCount    = 3,
            Padding     = new Padding(10, 6, 10, 6),
            BackColor   = Color.FromArgb(248, 249, 252),
        };
        tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        tbl.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 85));
        for (int i = 0; i < 3; i++)
            tbl.RowStyles.Add(new RowStyle(SizeType.Percent, 33.3f));

        // Row 0: History file
        tbl.Controls.Add(MakeSettingLabel("History File:"), 0, 0);
        _historyFileBox = new TextBox { Dock = DockStyle.Fill };
        _historyFileBox.TextChanged += (_, _) => { if (!_loading) { _settings.HistoryFilePath = _historyFileBox.Text; WriteSettingsFile(); } };
        tbl.Controls.Add(_historyFileBox, 1, 0);
        var browseHistBtn = MakeBtn("Browse...");
        browseHistBtn.Click += BrowseHistoryFile;
        tbl.Controls.Add(browseHistBtn, 2, 0);

        // Row 1: Python exe
        tbl.Controls.Add(MakeSettingLabel("Python Exe:"), 0, 1);
        _pythonExeBox = new TextBox { Dock = DockStyle.Fill };
        _pythonExeBox.TextChanged += (_, _) => { if (!_loading) { _settings.PythonExe = _pythonExeBox.Text; WriteSettingsFile(); } };
        tbl.Controls.Add(_pythonExeBox, 1, 1);
        tbl.Controls.Add(new Panel { Dock = DockStyle.Fill }, 2, 1);

        // Row 2: Project dir
        tbl.Controls.Add(MakeSettingLabel("Project Dir:"), 0, 2);
        _projectDirBox = new TextBox { Dock = DockStyle.Fill };
        _projectDirBox.TextChanged += (_, _) => { if (!_loading) { _settings.ProjectDir = _projectDirBox.Text; WriteSettingsFile(); } };
        tbl.Controls.Add(_projectDirBox, 1, 2);
        var browseProjBtn = MakeBtn("Browse...");
        browseProjBtn.Click += BrowseProjectDir;
        tbl.Controls.Add(browseProjBtn, 2, 2);

        parent.Controls.Add(tbl);
    }

    private void BuildTickerPanel(Panel parent)
    {
        // Header
        var header = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 32,
            BackColor = Color.FromArgb(22, 28, 42),
        };
        header.Controls.Add(new Label
        {
            Text      = "TICKER LIST",
            ForeColor = Color.FromArgb(150, 185, 240),
            Font      = new Font("Segoe UI", 9f, FontStyle.Bold),
            Dock      = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter,
        });

        // Button row: Load / Add / Remove
        var topButtons = new FlowLayoutPanel
        {
            Dock          = DockStyle.Top,
            Height        = 34,
            FlowDirection = FlowDirection.LeftToRight,
            Padding       = new Padding(4, 4, 4, 0),
            BackColor     = Color.FromArgb(248, 249, 252),
            WrapContents  = false,
        };
        var loadBtn = MakeSmallBtn("Load File…", 76);
        loadBtn.Click += LoadTickersFromFile;
        var addBtn = MakeSmallBtn("+ Add", 52);
        addBtn.Click += AddTicker;
        var removeBtn = MakeSmallBtn("Remove", 58);
        removeBtn.Click += RemoveSelectedTickers;
        topButtons.Controls.AddRange(new Control[] { loadBtn, addBtn, removeBtn });

        // Ticker checklist
        _tickerList = new CheckedListBox
        {
            Dock         = DockStyle.Fill,
            Font         = new Font("Consolas", 10.5f),
            CheckOnClick = true,
            BorderStyle  = BorderStyle.None,
            BackColor    = Color.White,
            IntegralHeight = false,
        };
        _tickerList.ItemCheck += (_, _) => BeginInvoke(SaveTickerList);

        // Bottom row: Select All / None
        var botButtons = new FlowLayoutPanel
        {
            Dock          = DockStyle.Bottom,
            Height        = 32,
            FlowDirection = FlowDirection.LeftToRight,
            Padding       = new Padding(4, 3, 4, 3),
            BackColor     = Color.FromArgb(248, 249, 252),
            WrapContents  = false,
        };
        var selectAllBtn = MakeSmallBtn("✓ All", 60);
        selectAllBtn.Click += (_, _) =>
        {
            for (int i = 0; i < _tickerList.Items.Count; i++) _tickerList.SetItemChecked(i, true);
            SaveTickerList();
        };
        var selectNoneBtn = MakeSmallBtn("○ None", 60);
        selectNoneBtn.Click += (_, _) =>
        {
            for (int i = 0; i < _tickerList.Items.Count; i++) _tickerList.SetItemChecked(i, false);
            SaveTickerList();
        };
        botButtons.Controls.AddRange(new Control[] { selectAllBtn, selectNoneBtn });

        // Add in reverse z-order (last added = topmost z = processed first for Top/Bottom)
        parent.Controls.Add(_tickerList);
        parent.Controls.Add(topButtons);
        parent.Controls.Add(header);
        parent.Controls.Add(botButtons);
    }

    private void BuildRightPanel(Panel parent)
    {
        // AI Provider config panel (top of right)
        var aiPanel = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 210,
            BackColor = Color.White,
        };
        BuildAiProviderPanel(aiPanel);

        // Horizontal rule
        var rule = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 1,
            BackColor = Color.FromArgb(210, 215, 228),
        };

        // Tab control: Current Session | Historical Analysis
        _mainTabControl = new TabControl
        {
            Dock    = DockStyle.Fill,
            Font    = new Font("Segoe UI", 9f),
            Padding = new Point(12, 4),
        };

        var sessionTab = new TabPage { Text = "  Current Session  ", UseVisualStyleBackColor = true };
        BuildCurrentSessionTab(sessionTab);

        var historyTab = new TabPage { Text = "  Historical Analysis  ", UseVisualStyleBackColor = true };
        BuildHistoryTab(historyTab);

        _mainTabControl.TabPages.AddRange(new[] { sessionTab, historyTab });
        _mainTabControl.SelectedIndexChanged += (_, _) =>
        {
            if (_mainTabControl.SelectedIndex == 1)
                LoadHistoryFromFile();
        };

        // Add in reverse z-order
        parent.Controls.Add(_mainTabControl);
        parent.Controls.Add(rule);
        parent.Controls.Add(aiPanel);
    }

    private void BuildCurrentSessionTab(TabPage parent)
    {
        var resultsSplit = new SplitContainer
        {
            Dock             = DockStyle.Fill,
            Orientation      = Orientation.Horizontal,
            SplitterDistance = 260,
            Panel1MinSize    = 100,
            Panel2MinSize    = 80,
            BackColor        = Color.FromArgb(240, 242, 246),
        };
        BuildResultsGrid(resultsSplit.Panel1);
        BuildReportBox(resultsSplit.Panel2);
        parent.Controls.Add(resultsSplit);
    }

    private void BuildHistoryTab(TabPage parent)
    {
        // ── Filter bar ───────────────────────────────────────────────────────
        var filterPanel = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 44,
            BackColor = Color.FromArgb(248, 249, 252),
        };

        int x = 10;
        filterPanel.Controls.Add(new Label
        {
            Text = "Ticker:", Location = new Point(x, 14), AutoSize = true,
            Font = new Font("Segoe UI", 8.5f), ForeColor = Color.FromArgb(60, 70, 95),
        });
        x += 50;

        _historyTickerFilter = new ComboBox
        {
            Location = new Point(x, 10), Width = 95,
            DropDownStyle = ComboBoxStyle.DropDown,
            Font = new Font("Consolas", 9f),
        };
        _historyTickerFilter.Items.Add("All Tickers");
        _historyTickerFilter.SelectedIndex = 0;
        _historyTickerFilter.SelectedIndexChanged += (_, _) => { if (!_loading) LoadHistoryFromFile(); };
        filterPanel.Controls.Add(_historyTickerFilter);
        x += 103;

        filterPanel.Controls.Add(new Label
        {
            Text = "From:", Location = new Point(x, 14), AutoSize = true,
            Font = new Font("Segoe UI", 8.5f), ForeColor = Color.FromArgb(60, 70, 95),
        });
        x += 40;
        _historyFromDate = new DateTimePicker
        {
            Location = new Point(x, 10), Width = 100,
            Format = DateTimePickerFormat.Short, Value = DateTime.Now.AddMonths(-3),
        };
        filterPanel.Controls.Add(_historyFromDate);
        x += 108;

        filterPanel.Controls.Add(new Label
        {
            Text = "To:", Location = new Point(x, 14), AutoSize = true,
            Font = new Font("Segoe UI", 8.5f), ForeColor = Color.FromArgb(60, 70, 95),
        });
        x += 28;
        _historyToDate = new DateTimePicker
        {
            Location = new Point(x, 10), Width = 100,
            Format = DateTimePickerFormat.Short, Value = DateTime.Now,
        };
        filterPanel.Controls.Add(_historyToDate);
        x += 108;

        var refreshBtn = new Button
        {
            Text = "⟳  Refresh", Location = new Point(x, 9), Width = 90, Height = 26,
            FlatStyle = FlatStyle.Flat, BackColor = Color.FromArgb(0, 115, 207),
            ForeColor = Color.White, Cursor = Cursors.Hand, Font = new Font("Segoe UI", 8.5f),
        };
        refreshBtn.FlatAppearance.BorderSize = 0;
        refreshBtn.Click += (_, _) => LoadHistoryFromFile();
        filterPanel.Controls.Add(refreshBtn);
        x += 98;

        var exportBtn = new Button
        {
            Text = "↓  Export CSV", Location = new Point(x, 9), Width = 108, Height = 26,
            FlatStyle = FlatStyle.Flat, BackColor = Color.FromArgb(65, 90, 135),
            ForeColor = Color.White, Cursor = Cursors.Hand, Font = new Font("Segoe UI", 8.5f),
        };
        exportBtn.FlatAppearance.BorderSize = 0;
        exportBtn.Click += ExportHistoryToCsv;
        filterPanel.Controls.Add(exportBtn);

        // ── Summary bar ──────────────────────────────────────────────────────
        var summaryPanel = new Panel
        {
            Dock = DockStyle.Bottom, Height = 26,
            BackColor = Color.FromArgb(30, 38, 58),
        };
        _historySummaryLabel = new Label
        {
            Dock = DockStyle.Fill,
            ForeColor = Color.FromArgb(150, 185, 235),
            Font = new Font("Segoe UI", 8f),
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(10, 0, 0, 0),
        };
        summaryPanel.Controls.Add(_historySummaryLabel);

        // ── History DataGridView ─────────────────────────────────────────────
        var hdrStyle = new DataGridViewCellStyle
        {
            BackColor = Color.FromArgb(40, 50, 72), ForeColor = Color.FromArgb(180, 200, 230),
            Font = new Font("Segoe UI", 8.5f, FontStyle.Bold),
            SelectionBackColor = Color.FromArgb(40, 50, 72),
            SelectionForeColor = Color.FromArgb(180, 200, 230),
        };
        _historyGrid = new DataGridView
        {
            Dock                          = DockStyle.Fill,
            ReadOnly                      = true,
            AllowUserToAddRows            = false,
            AllowUserToDeleteRows         = false,
            AutoSizeColumnsMode           = DataGridViewAutoSizeColumnsMode.Fill,
            SelectionMode                 = DataGridViewSelectionMode.FullRowSelect,
            RowHeadersVisible             = false,
            BackgroundColor               = Color.White,
            BorderStyle                   = BorderStyle.None,
            GridColor                     = Color.FromArgb(225, 230, 240),
            Font                          = new Font("Segoe UI", 8.5f),
            ColumnHeadersDefaultCellStyle = hdrStyle,
            EnableHeadersVisualStyles     = false,
            ColumnHeadersHeight           = 26,
            RowTemplate                   = { Height = 23 },
            DefaultCellStyle              = { SelectionBackColor = Color.FromArgb(215, 230, 252), SelectionForeColor = Color.Black },
            AllowUserToOrderColumns       = true,
        };

        DataGridViewTextBoxColumn HC(string name, string hdr, int fw)
        {
            var c = new DataGridViewTextBoxColumn { Name = name, HeaderText = hdr, FillWeight = fw };
            c.SortMode = DataGridViewColumnSortMode.Programmatic;
            return c;
        }
        _historyGrid.Columns.AddRange(
            HC("RunAt",      "Date / Time (UTC)", 118),
            HC("HTicker",    "Ticker",              58),
            HC("HSignal",    "Signal",             140),
            HC("HConf",      "Conf",                42),
            HC("HSentiment", "Sentiment",            68),
            HC("HClose",     "Close ($)",            65),
            HC("HReturn7d",  "7d Ret %",             62),
            HC("HVsSMA7",    "vs SMA7",              55),
            HC("HRSI14",     "RSI-14",               48)
        );
        _historyGrid.ColumnHeaderMouseClick += HistoryGrid_ColumnHeaderClick;

        // Add in reverse z-order (last added = z=0 = processed first)
        // Want: filterPanel top, _historyGrid fill, summaryPanel bottom
        // So: _historyGrid first, filterPanel second, summaryPanel last
        parent.Controls.Add(_historyGrid);
        parent.Controls.Add(filterPanel);
        parent.Controls.Add(summaryPanel);
    }

    private void BuildAiProviderPanel(Panel parent)
    {
        // Section header
        var header = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 28,
            BackColor = Color.FromArgb(22, 28, 42),
        };
        header.Controls.Add(new Label
        {
            Text      = "AI PROVIDER & CONFIGURATION",
            ForeColor = Color.FromArgb(150, 185, 240),
            Font      = new Font("Segoe UI", 9f, FontStyle.Bold),
            Dock      = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter,
        });

        // Provider rows table: [Radio 120] [Key TextBox %] [Eye 34] [Model 140]
        var providerTable = new TableLayoutPanel
        {
            Dock        = DockStyle.Top,
            Height      = 136,
            ColumnCount = 4,
            RowCount    = 4,
            Padding     = new Padding(8, 4, 8, 0),
            BackColor   = Color.White,
        };
        providerTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
        providerTable.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        providerTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 34));
        providerTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 145));
        for (int i = 0; i < 4; i++)
            providerTable.RowStyles.Add(new RowStyle(SizeType.Percent, 25f));

        AddProviderRow(providerTable, 0, "OpenAI",        "gpt-4o-mini",
            out _radioOpenAI,     out _openaiKeyBox,     out _openaiModelBox);
        AddProviderRow(providerTable, 1, "Claude",         "claude-opus-4-6",
            out _radioClaude,     out _claudeKeyBox,     out _claudeModelBox);
        AddProviderRow(providerTable, 2, "Google Gemini",  "gemini-1.5-flash",
            out _radioGoogle,     out _googleKeyBox,     out _googleModelBox);
        AddProviderRow(providerTable, 3, "Perplexity",     "sonar",
            out _radioPerplexity, out _perplexityKeyBox, out _perplexityModelBox);

        foreach (var rb in new[] { _radioOpenAI, _radioClaude, _radioGoogle, _radioPerplexity })
            rb.CheckedChanged += ProviderChanged;

        // Bottom config + run row
        var configRow = new Panel
        {
            Dock      = DockStyle.Fill,
            BackColor = Color.FromArgb(248, 249, 252),
            Padding   = new Padding(8, 0, 8, 0),
        };

        var threshLabel = new Label
        {
            Text      = "Confidence threshold:",
            AutoSize  = true,
            Location  = new Point(0, 12),
            ForeColor = Color.FromArgb(80, 90, 115),
            Font      = new Font("Segoe UI", 8.5f),
        };
        _confidenceNum = new NumericUpDown
        {
            Minimum  = 0,
            Maximum  = 100,
            Value    = 40,
            Width    = 52,
            Location = new Point(148, 9),
            Font     = new Font("Segoe UI", 9f),
        };
        _confidenceNum.ValueChanged += (_, _) =>
        {
            if (!_loading) { _settings.ConfidenceThreshold = (int)_confidenceNum.Value; WriteSettingsFile(); }
        };

        _runBtn = new Button
        {
            Text      = "▶  Run Selected Tickers",
            Location  = new Point(215, 6),
            Width     = 195,
            Height    = 32,
            Font      = new Font("Segoe UI", 9.5f, FontStyle.Bold),
            BackColor = Color.FromArgb(0, 115, 207),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Cursor    = Cursors.Hand,
        };
        _runBtn.FlatAppearance.BorderSize = 0;
        _runBtn.Click += RunSelectedTickers;

        _progressBar = new ProgressBar
        {
            Location = new Point(420, 11),
            Width    = 180,
            Height   = 20,
            Visible  = false,
            Style    = ProgressBarStyle.Continuous,
        };

        _progressLabel = new Label
        {
            Location  = new Point(608, 13),
            AutoSize  = true,
            ForeColor = Color.FromArgb(80, 100, 140),
            Font      = new Font("Segoe UI", 8.5f),
            Visible   = false,
        };

        configRow.Controls.AddRange(new Control[]
            { threshLabel, _confidenceNum, _runBtn, _progressBar, _progressLabel });

        // Add in reverse z-order
        parent.Controls.Add(configRow);
        parent.Controls.Add(providerTable);
        parent.Controls.Add(header);
    }

    private void AddProviderRow(
        TableLayoutPanel table, int row, string name, string defaultModel,
        out RadioButton radio, out TextBox keyBox, out TextBox modelBox)
    {
        radio = new RadioButton
        {
            Text      = name,
            Dock      = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft,
            Font      = new Font("Segoe UI", 9f),
            ForeColor = Color.FromArgb(40, 50, 70),
        };
        table.Controls.Add(radio, 0, row);

        keyBox = new TextBox
        {
            Dock                  = DockStyle.Fill,
            UseSystemPasswordChar = true,
            PlaceholderText       = $"{name} API Key",
            Font                  = new Font("Consolas", 8.5f),
            ForeColor             = Color.FromArgb(40, 50, 70),
        };
        keyBox.TextChanged += (_, _) => { if (!_loading) SaveApiKeys(); };
        table.Controls.Add(keyBox, 1, row);

        var eyeBtn = new Button
        {
            Text      = "👁",
            Dock      = DockStyle.Fill,
            FlatStyle = FlatStyle.Flat,
            Cursor    = Cursors.Hand,
            Font      = new Font("Segoe UI", 9f),
            ForeColor = Color.FromArgb(80, 100, 140),
        };
        eyeBtn.FlatAppearance.BorderSize  = 0;
        eyeBtn.FlatAppearance.MouseOverBackColor = Color.FromArgb(220, 230, 245);
        var capturedKey = keyBox;
        eyeBtn.Click += (_, _) => capturedKey.UseSystemPasswordChar = !capturedKey.UseSystemPasswordChar;
        table.Controls.Add(eyeBtn, 2, row);

        modelBox = new TextBox
        {
            Dock      = DockStyle.Fill,
            Text      = defaultModel,
            Font      = new Font("Consolas", 8f),
            ForeColor = Color.FromArgb(90, 100, 130),
        };
        modelBox.TextChanged += (_, _) => { if (!_loading) SaveModelSettings(); };
        table.Controls.Add(modelBox, 3, row);
    }

    private void BuildResultsGrid(SplitterPanel parent)
    {
        var header = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 26,
            BackColor = Color.FromArgb(22, 28, 42),
        };
        header.Controls.Add(new Label
        {
            Text      = "ANALYSIS RESULTS",
            ForeColor = Color.FromArgb(150, 185, 240),
            Font      = new Font("Segoe UI", 9f, FontStyle.Bold),
            Dock      = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter,
        });

        var headerStyle = new DataGridViewCellStyle
        {
            BackColor = Color.FromArgb(40, 50, 72),
            ForeColor = Color.FromArgb(180, 200, 230),
            Font      = new Font("Segoe UI", 8.5f, FontStyle.Bold),
            SelectionBackColor = Color.FromArgb(40, 50, 72),
            SelectionForeColor = Color.FromArgb(180, 200, 230),
        };

        _resultsGrid = new DataGridView
        {
            Dock                            = DockStyle.Fill,
            ReadOnly                        = true,
            AllowUserToAddRows              = false,
            AllowUserToDeleteRows           = false,
            AutoSizeColumnsMode             = DataGridViewAutoSizeColumnsMode.Fill,
            SelectionMode                   = DataGridViewSelectionMode.FullRowSelect,
            RowHeadersVisible               = false,
            BackgroundColor                 = Color.White,
            BorderStyle                     = BorderStyle.None,
            GridColor                       = Color.FromArgb(225, 230, 240),
            Font                            = new Font("Segoe UI", 8.5f),
            ColumnHeadersDefaultCellStyle   = headerStyle,
            EnableHeadersVisualStyles       = false,
            ColumnHeadersHeight             = 26,
            RowTemplate                     = { Height = 24 },
            DefaultCellStyle                = { SelectionBackColor = Color.FromArgb(220, 232, 250), SelectionForeColor = Color.Black },
        };
        _resultsGrid.Columns.AddRange(
            new DataGridViewTextBoxColumn { Name = "Num",        HeaderText = "#",          FillWeight = 28  },
            new DataGridViewTextBoxColumn { Name = "Ticker",     HeaderText = "Ticker",     FillWeight = 65  },
            new DataGridViewTextBoxColumn { Name = "Status",     HeaderText = "Status",     FillWeight = 90  },
            new DataGridViewTextBoxColumn { Name = "Signal",     HeaderText = "Signal",     FillWeight = 145 },
            new DataGridViewTextBoxColumn { Name = "Confidence", HeaderText = "Conf",       FillWeight = 44  },
            new DataGridViewTextBoxColumn { Name = "Sentiment",  HeaderText = "Sentiment",  FillWeight = 70  },
            new DataGridViewTextBoxColumn { Name = "Close",      HeaderText = "Close ($)",  FillWeight = 70  },
            new DataGridViewTextBoxColumn { Name = "Return7d",   HeaderText = "7d Ret %",   FillWeight = 65  },
            new DataGridViewTextBoxColumn { Name = "VsSMA7",     HeaderText = "vs SMA7",    FillWeight = 55  },
            new DataGridViewTextBoxColumn { Name = "Provider",   HeaderText = "Provider",   FillWeight = 72  }
        );
        _resultsGrid.SelectionChanged += ResultsGrid_SelectionChanged;
        _resultsGrid.CellFormatting   += ResultsGrid_CellFormatting;

        parent.Controls.Add(_resultsGrid);
        parent.Controls.Add(header);
    }

    private void BuildReportBox(SplitterPanel parent)
    {
        var header = new Panel
        {
            Dock      = DockStyle.Top,
            Height    = 26,
            BackColor = Color.FromArgb(22, 28, 42),
        };
        header.Controls.Add(new Label
        {
            Text      = "ANALYSIS DETAIL",
            ForeColor = Color.FromArgb(150, 185, 240),
            Font      = new Font("Segoe UI", 9f, FontStyle.Bold),
            Dock      = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter,
        });

        _reportBox = new RichTextBox
        {
            Dock        = DockStyle.Fill,
            ReadOnly    = true,
            ScrollBars  = RichTextBoxScrollBars.Both,
            WordWrap    = false,
            Font        = new Font("Consolas", 9f),
            BackColor   = Color.FromArgb(16, 20, 30),
            ForeColor   = Color.FromArgb(175, 210, 255),
            BorderStyle = BorderStyle.None,
        };

        parent.Controls.Add(_reportBox);
        parent.Controls.Add(header);
    }

    // -----------------------------------------------------------------------
    // Settings persistence
    // -----------------------------------------------------------------------

    private void LoadSettings()
    {
        _loading = true;
        try
        {
            if (File.Exists(_settingsPath))
            {
                var json = File.ReadAllText(_settingsPath);
                _settings = JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
            }

            _historyFileBox.Text = _settings.HistoryFilePath;
            _pythonExeBox.Text   = string.IsNullOrEmpty(_settings.PythonExe) ? "python" : _settings.PythonExe;
            _projectDirBox.Text  = _settings.ProjectDir;

            _openaiKeyBox.Text     = _settings.OpenAiKey;
            _claudeKeyBox.Text     = _settings.ClaudeKey;
            _googleKeyBox.Text     = _settings.GoogleKey;
            _perplexityKeyBox.Text = _settings.PerplexityKey;

            _openaiModelBox.Text     = _settings.OpenAiModel.Length     > 0 ? _settings.OpenAiModel     : "gpt-4o-mini";
            _claudeModelBox.Text     = _settings.ClaudeModel.Length     > 0 ? _settings.ClaudeModel     : "claude-opus-4-6";
            _googleModelBox.Text     = _settings.GoogleModel.Length     > 0 ? _settings.GoogleModel     : "gemini-1.5-flash";
            _perplexityModelBox.Text = _settings.PerplexityModel.Length > 0 ? _settings.PerplexityModel : "sonar";

            _confidenceNum.Value = Math.Clamp(_settings.ConfidenceThreshold, 0, 100);

            switch (_settings.AiProvider.ToLowerInvariant())
            {
                case "claude":     _radioClaude.Checked     = true; break;
                case "google":     _radioGoogle.Checked     = true; break;
                case "perplexity": _radioPerplexity.Checked = true; break;
                default:           _radioOpenAI.Checked     = true; break;
            }

            // Tickers
            _tickerList.Items.Clear();
            foreach (var t in _settings.Tickers)
                _tickerList.Items.Add(t, true);
        }
        catch { /* use defaults */ }
        finally { _loading = false; }
    }

    private void SaveApiKeys()
    {
        _settings.OpenAiKey     = _openaiKeyBox.Text;
        _settings.ClaudeKey     = _claudeKeyBox.Text;
        _settings.GoogleKey     = _googleKeyBox.Text;
        _settings.PerplexityKey = _perplexityKeyBox.Text;
        WriteSettingsFile();
    }

    private void SaveModelSettings()
    {
        _settings.OpenAiModel     = _openaiModelBox.Text;
        _settings.ClaudeModel     = _claudeModelBox.Text;
        _settings.GoogleModel     = _googleModelBox.Text;
        _settings.PerplexityModel = _perplexityModelBox.Text;
        WriteSettingsFile();
    }

    private void SaveTickerList()
    {
        _settings.Tickers = _tickerList.Items.Cast<string>().ToList();
        WriteSettingsFile();
    }

    private void WriteSettingsFile()
    {
        try
        {
            var json = JsonSerializer.Serialize(_settings,
                new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(_settingsPath, json);
        }
        catch { /* swallow */ }
    }

    // -----------------------------------------------------------------------
    // Provider selection
    // -----------------------------------------------------------------------

    private void ProviderChanged(object? sender, EventArgs e)
    {
        if (_loading) return;
        if (sender is not RadioButton { Checked: true } rb) return;

        _settings.AiProvider = rb.Text.ToLowerInvariant() switch
        {
            "claude"        => "claude",
            "google gemini" => "google",
            "perplexity"    => "perplexity",
            _               => "openai",
        };
        WriteSettingsFile();
    }

    // -----------------------------------------------------------------------
    // Settings panel toggle
    // -----------------------------------------------------------------------

    private void ToggleSettings(object? sender, EventArgs e)
    {
        _settingsPanel.Visible = !_settingsPanel.Visible;
        _settingsToggle.Text = _settingsPanel.Visible ? "⚙  Hide Settings" : "⚙  Settings";
    }

    // -----------------------------------------------------------------------
    // Auto-detect history + project dir
    // -----------------------------------------------------------------------

    private void AutoDetectHistoryFile()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, "data", "signal_history.jsonl");
            if (File.Exists(candidate))
            {
                _settings.HistoryFilePath = candidate;
                _settings.ProjectDir      = dir.FullName;
                _historyFileBox.Text      = candidate;
                _projectDirBox.Text       = dir.FullName;
                WriteSettingsFile();
                SetStatus($"Auto-detected project at {dir.FullName}");
                return;
            }
            dir = dir.Parent;
        }
    }

    // -----------------------------------------------------------------------
    // Browse buttons
    // -----------------------------------------------------------------------

    private void BrowseHistoryFile(object? sender, EventArgs e)
    {
        using var dlg = new OpenFileDialog
        {
            Title  = "Select signal_history.jsonl",
            Filter = "JSONL files (*.jsonl)|*.jsonl|All files (*.*)|*.*",
        };
        if (!string.IsNullOrEmpty(_settings.HistoryFilePath))
            dlg.InitialDirectory = Path.GetDirectoryName(_settings.HistoryFilePath) ?? "";
        if (dlg.ShowDialog() == DialogResult.OK)
        {
            _historyFileBox.Text = dlg.FileName;
            _settings.HistoryFilePath = dlg.FileName;
            WriteSettingsFile();
        }
    }

    private void BrowseProjectDir(object? sender, EventArgs e)
    {
        using var dlg = new FolderBrowserDialog
        {
            Description = "Select the project root directory (where src/ lives)",
        };
        if (!string.IsNullOrEmpty(_settings.ProjectDir))
            dlg.InitialDirectory = _settings.ProjectDir;
        if (dlg.ShowDialog() == DialogResult.OK)
        {
            _projectDirBox.Text = dlg.SelectedPath;
            _settings.ProjectDir = dlg.SelectedPath;
            WriteSettingsFile();
        }
    }

    // -----------------------------------------------------------------------
    // Ticker list management
    // -----------------------------------------------------------------------

    private void LoadTickersFromFile(object? sender, EventArgs e)
    {
        using var dlg = new OpenFileDialog
        {
            Title  = "Load Ticker List",
            Filter = "CSV files (*.csv)|*.csv|Text files (*.txt)|*.txt|All files (*.*)|*.*",
        };
        if (dlg.ShowDialog() != DialogResult.OK) return;

        try
        {
            var lines = File.ReadAllLines(dlg.FileName, Encoding.UTF8);
            var newTickers = lines
                .SelectMany(l => l.Split(new[] { ',', ';', '\t', ' ' }, StringSplitOptions.RemoveEmptyEntries))
                .Select(t => t.Trim().ToUpperInvariant())
                .Where(t => t.Length >= 1 && t.Length <= 10 && t.All(c => char.IsLetterOrDigit(c) || c == '.' || c == '-'))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();

            if (newTickers.Count == 0)
            {
                MessageBox.Show("No valid ticker symbols found in the file.\n\nExpected format: one ticker per line, or comma-separated.",
                    "No Tickers Found", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var existing = _tickerList.Items.Cast<string>().ToHashSet(StringComparer.OrdinalIgnoreCase);
            int added = 0;
            foreach (var t in newTickers)
            {
                if (!existing.Contains(t))
                {
                    _tickerList.Items.Add(t, true);
                    added++;
                }
            }
            SaveTickerList();
            SetStatus($"Loaded {added} new ticker(s) from \"{Path.GetFileName(dlg.FileName)}\" — {_tickerList.Items.Count} total.");
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Failed to read file:\n{ex.Message}", "Error",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void AddTicker(object? sender, EventArgs e)
    {
        using var dlg = new AddTickerDialog();
        if (dlg.ShowDialog() != DialogResult.OK) return;
        var ticker = dlg.Ticker;
        if (string.IsNullOrEmpty(ticker)) return;

        var existing = _tickerList.Items.Cast<string>().ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (existing.Contains(ticker))
        {
            SetStatus($"{ticker} is already in the list.");
            return;
        }
        _tickerList.Items.Add(ticker, true);
        SaveTickerList();
        SetStatus($"Added {ticker}. Total: {_tickerList.Items.Count} tickers.");
    }

    private void RemoveSelectedTickers(object? sender, EventArgs e)
    {
        var toRemove = _tickerList.SelectedItems.Cast<string>().ToList();
        if (toRemove.Count == 0)
        {
            SetStatus("Select one or more tickers to remove first.");
            return;
        }
        if (MessageBox.Show($"Remove {toRemove.Count} ticker(s) from the list?",
            "Confirm Remove", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            return;

        foreach (var t in toRemove)
            _tickerList.Items.Remove(t);
        SaveTickerList();
        SetStatus($"Removed {toRemove.Count} ticker(s). {_tickerList.Items.Count} remaining.");
    }

    // -----------------------------------------------------------------------
    // Run analysis for all selected tickers
    // -----------------------------------------------------------------------

    private void RunSelectedTickers(object? sender, EventArgs e)
    {
        var selected = _tickerList.CheckedItems.Cast<string>().ToList();
        if (selected.Count == 0)
        {
            MessageBox.Show("No tickers selected.\nCheck at least one ticker in the list.",
                "Nothing to Run", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var projectDir = _projectDirBox.Text.Trim();
        if (string.IsNullOrEmpty(projectDir) || !Directory.Exists(projectDir))
        {
            MessageBox.Show("Set a valid Project Dir in Settings first.\n\nClick \"⚙ Settings\" to configure.",
                "Missing Configuration", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        // Cancel any previous run
        _cts?.Cancel();
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;

        // Setup UI
        _runBtn.Enabled    = false;
        _runBtn.Text       = "⏹  Cancel Run";
        _runBtn.BackColor  = Color.FromArgb(180, 40, 40);
        _runBtn.Click     -= RunSelectedTickers;
        _runBtn.Click     += CancelRun;

        _progressBar.Minimum = 0;
        _progressBar.Maximum = selected.Count;
        _progressBar.Value   = 0;
        _progressBar.Visible = true;
        _progressLabel.Visible = true;

        // Initialize results grid
        _resultsGrid.Rows.Clear();
        _reportCache.Clear();
        _reportBox.Clear();

        var provider = GetSelectedProvider();
        for (int i = 0; i < selected.Count; i++)
        {
            _resultsGrid.Rows.Add(
                (i + 1).ToString(), selected[i], "Pending",
                "", "", "", "", "", "", provider);
            _resultsGrid.Rows[i].DefaultCellStyle.BackColor =
                i % 2 == 0 ? Color.White : Color.FromArgb(248, 250, 255);
            SetRowStatus(i, "Pending", Color.FromArgb(150, 155, 175));
        }

        var pythonExe = _pythonExeBox.Text.Trim();
        var envVars   = BuildEnvVars();

        Task.Run(async () =>
        {
            for (int i = 0; i < selected.Count; i++)
            {
                if (ct.IsCancellationRequested) break;

                var ticker   = selected[i];
                var rowIndex = i;

                Invoke(() =>
                {
                    SetRowStatus(rowIndex, "⟳ Running…", Color.FromArgb(0, 140, 200));
                    _progressLabel.Text = $"{ticker}  [{i + 1} / {selected.Count}]";
                    SetStatus($"Analyzing {ticker}…  [{i + 1} of {selected.Count}]");
                });

                var (output, exitCode) = await RunPythonAsync(pythonExe, projectDir, ticker, envVars, ct);

                if (ct.IsCancellationRequested) break;

                var record = ReadLatestHistoryRecord(_settings.HistoryFilePath, ticker);

                Invoke(() =>
                {
                    _reportCache[ticker] = output;
                    if (exitCode == 0 && record.HasValue)
                        UpdateResultRow(rowIndex, record.Value, provider);
                    else
                        SetRowStatus(rowIndex, exitCode != 0 ? "✗ Error" : "? No data", Color.DarkRed);

                    _progressBar.Value   = i + 1;
                    _progressLabel.Text  = $"{ticker}  [{i + 1} / {selected.Count}]";
                });
            }

            Invoke(() =>
            {
                RestoreRunButton();
                _progressBar.Visible   = false;
                _progressLabel.Visible = false;
                SetStatus(ct.IsCancellationRequested
                    ? "Run cancelled."
                    : $"Done — {selected.Count} ticker(s) analyzed.");
                LoadHistoryFromFile(); // refresh history cache after run
            });
        }, ct);
    }

    private void CancelRun(object? sender, EventArgs e)
    {
        _cts?.Cancel();
        RestoreRunButton();
        SetStatus("Cancelling…");
    }

    private void RestoreRunButton()
    {
        _runBtn.Click    -= CancelRun;
        _runBtn.Click    += RunSelectedTickers;
        _runBtn.Enabled   = true;
        _runBtn.Text      = "▶  Run Selected Tickers";
        _runBtn.BackColor = Color.FromArgb(0, 115, 207);
    }

    // -----------------------------------------------------------------------
    // Python subprocess
    // -----------------------------------------------------------------------

    private static async Task<(string output, int exitCode)> RunPythonAsync(
        string pythonExe, string projectDir, string ticker,
        Dictionary<string, string> extraEnv, CancellationToken ct)
    {
        var psi = new ProcessStartInfo
        {
            FileName               = pythonExe,
            Arguments              = "-m src.main",
            WorkingDirectory       = projectDir,
            UseShellExecute        = false,
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            CreateNoWindow         = true,
        };
        psi.Environment["TICKER"] = ticker;
        psi.Environment["TOPIC"]  = ticker;
        foreach (var kv in extraEnv)
            psi.Environment[kv.Key] = kv.Value;

        var output = new StringBuilder();
        try
        {
            using var proc = new Process { StartInfo = psi };
            proc.OutputDataReceived += (_, e) => { if (e.Data != null) output.AppendLine(e.Data); };
            proc.ErrorDataReceived  += (_, e) => { if (e.Data != null) output.AppendLine("[ERR] " + e.Data); };
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            try
            {
                await proc.WaitForExitAsync(ct);
            }
            catch (OperationCanceledException)
            {
                try { proc.Kill(entireProcessTree: true); } catch { }
                return (output.ToString(), -1);
            }

            return (output.ToString(), proc.ExitCode);
        }
        catch (Exception ex)
        {
            return ($"Failed to start Python:\n{ex.Message}", -2);
        }
    }

    private string GetSelectedProvider()
    {
        if (_radioClaude.Checked)     return "Claude";
        if (_radioGoogle.Checked)     return "Google";
        if (_radioPerplexity.Checked) return "Perplexity";
        return "OpenAI";
    }

    private Dictionary<string, string> BuildEnvVars() => new()
    {
        ["AI_PROVIDER"]          = _settings.AiProvider,
        ["OPENAI_API_KEY"]       = _openaiKeyBox.Text,
        ["OPENAI_MODEL"]         = _openaiModelBox.Text,
        ["CLAUDE_API_KEY"]       = _claudeKeyBox.Text,
        ["CLAUDE_MODEL"]         = _claudeModelBox.Text,
        ["GOOGLE_API_KEY"]       = _googleKeyBox.Text,
        ["GOOGLE_MODEL"]         = _googleModelBox.Text,
        ["PERPLEXITY_API_KEY"]   = _perplexityKeyBox.Text,
        ["PERPLEXITY_MODEL"]     = _perplexityModelBox.Text,
        ["CONFIDENCE_THRESHOLD"] = ((int)_confidenceNum.Value).ToString(),
    };

    // -----------------------------------------------------------------------
    // Results grid updates
    // -----------------------------------------------------------------------

    private void UpdateResultRow(int rowIndex, JsonElement r, string provider)
    {
        if (rowIndex >= _resultsGrid.Rows.Count) return;

        var signal    = GetStr(r, "final_signal");
        var conf      = GetStr(r, "confidence_0_100");
        var sentiment = GetStr(r, "news_sentiment");
        var close     = r.TryGetProperty("last_close",    out var cp) ? $"{cp.GetDouble():F2}" : "";
        var ret7d     = r.TryGetProperty("return_7d_pct", out var rp) ? $"{rp.GetDouble():+0.00;-0.00}%" : "";
        var vsSma7    = GetStr(r, "close_vs_sma7");

        var row = _resultsGrid.Rows[rowIndex];
        row.Cells["Status"].Value     = "✓ Done";
        row.Cells["Signal"].Value     = signal.Replace("_", " ").ToUpperInvariant();
        row.Cells["Confidence"].Value = conf;
        row.Cells["Sentiment"].Value  = sentiment;
        row.Cells["Close"].Value      = close;
        row.Cells["Return7d"].Value   = ret7d;
        row.Cells["VsSMA7"].Value     = vsSma7;

        row.Cells["Status"].Style.ForeColor = Color.FromArgb(0, 150, 80);
        row.Cells["Signal"].Style.Font      = new Font("Segoe UI", 8.5f, FontStyle.Bold);
        row.Cells["Signal"].Style.ForeColor = signal switch
        {
            "high_conviction_up"   => Color.FromArgb(0, 155, 75),
            "likely_up"            => Color.FromArgb(30, 130, 60),
            "high_conviction_down" => Color.FromArgb(180, 0, 0),
            "likely_down"          => Color.FromArgb(200, 40, 40),
            _                      => Color.FromArgb(180, 110, 0),
        };
    }

    private void SetRowStatus(int rowIndex, string status, Color color)
    {
        if (rowIndex >= _resultsGrid.Rows.Count) return;
        _resultsGrid.Rows[rowIndex].Cells["Status"].Value            = status;
        _resultsGrid.Rows[rowIndex].Cells["Status"].Style.ForeColor  = color;
    }

    private void ResultsGrid_CellFormatting(object? sender, DataGridViewCellFormattingEventArgs e)
    {
        // Alternate row background (set at add time; re-apply if needed)
    }

    private void ResultsGrid_SelectionChanged(object? sender, EventArgs e)
    {
        if (_resultsGrid.SelectedRows.Count == 0) return;
        var ticker = _resultsGrid.SelectedRows[0].Cells["Ticker"].Value?.ToString() ?? "";
        if (string.IsNullOrEmpty(ticker)) return;

        _reportBox.Text = _reportCache.TryGetValue(ticker, out var report)
            ? report
            : $"No report available for {ticker} yet.\n\nRun analysis first.";
    }

    // -----------------------------------------------------------------------
    // History helpers
    // -----------------------------------------------------------------------

    private static JsonElement? ReadLatestHistoryRecord(string path, string ticker)
    {
        if (!File.Exists(path)) return null;

        JsonElement? latest = null;
        var latestTime = DateTimeOffset.MinValue;

        try
        {
            foreach (var line in File.ReadLines(path, Encoding.UTF8))
            {
                var trimmed = line.Trim();
                if (string.IsNullOrEmpty(trimmed)) continue;
                try
                {
                    var doc  = JsonDocument.Parse(trimmed);
                    var root = doc.RootElement;
                    if (!root.TryGetProperty("ticker", out var tp)) continue;
                    if (!string.Equals(tp.GetString(), ticker, StringComparison.OrdinalIgnoreCase)) continue;
                    if (root.TryGetProperty("run_at", out var ra) &&
                        DateTimeOffset.TryParse(ra.GetString(), out var dt) && dt > latestTime)
                    {
                        latestTime = dt;
                        latest     = root.Clone();
                    }
                }
                catch { /* skip malformed lines */ }
            }
        }
        catch { /* swallow file errors */ }

        return latest;
    }

    private static string GetStr(JsonElement el, string key) =>
        el.TryGetProperty(key, out var p) ? p.ToString() : "";

    // -----------------------------------------------------------------------
    // History tab — load, filter, sort, export
    // -----------------------------------------------------------------------

    private void LoadHistoryFromFile()
    {
        var path = _historyFileBox?.Text.Trim() ?? "";
        if (!File.Exists(path))
        {
            if (_historyGrid != null) _historyGrid.Rows.Clear();
            if (_historySummaryLabel != null)
                _historySummaryLabel.Text = $"  History file not found: {(string.IsNullOrEmpty(path) ? "(not configured)" : path)}";
            return;
        }

        // ── Read all records from file ───────────────────────────────────────
        var all = new List<JsonElement>();
        try
        {
            foreach (var line in File.ReadLines(path, Encoding.UTF8))
            {
                var trimmed = line.Trim();
                if (string.IsNullOrEmpty(trimmed)) continue;
                try { all.Add(JsonDocument.Parse(trimmed).RootElement.Clone()); }
                catch { /* skip malformed */ }
            }
        }
        catch (Exception ex)
        {
            _historySummaryLabel.Text = $"  Error reading file: {ex.Message}";
            return;
        }

        // ── Update ticker dropdown ───────────────────────────────────────────
        var uniqueTickers = all
            .Where(r => r.TryGetProperty("ticker", out _))
            .Select(r => r.GetProperty("ticker").GetString() ?? "")
            .Where(t => t.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(t => t)
            .ToList();

        var prevSelection = _historyTickerFilter.Text;
        _loading = true;
        _historyTickerFilter.Items.Clear();
        _historyTickerFilter.Items.Add("All Tickers");
        foreach (var t in uniqueTickers) _historyTickerFilter.Items.Add(t);
        _historyTickerFilter.Text = uniqueTickers.Contains(prevSelection, StringComparer.OrdinalIgnoreCase)
            ? prevSelection : "All Tickers";
        _loading = false;

        // ── Apply filters ────────────────────────────────────────────────────
        var tickerFilter = _historyTickerFilter.Text.Trim();
        var filterByTicker = !string.IsNullOrEmpty(tickerFilter) &&
                             !tickerFilter.Equals("All Tickers", StringComparison.OrdinalIgnoreCase);
        var fromUtc = _historyFromDate.Value.Date.ToUniversalTime();
        var toUtc   = _historyToDate.Value.Date.AddDays(1).ToUniversalTime(); // inclusive

        var filtered = all.Where(r =>
        {
            if (filterByTicker)
            {
                if (!r.TryGetProperty("ticker", out var tp)) return false;
                if (!string.Equals(tp.GetString(), tickerFilter, StringComparison.OrdinalIgnoreCase)) return false;
            }
            if (r.TryGetProperty("run_at", out var ra) &&
                DateTimeOffset.TryParse(ra.GetString(), out var dt))
            {
                var utc = dt.UtcDateTime;
                return utc >= fromUtc && utc < toUtc;
            }
            return true;
        }).ToList();

        // ── Sort (default: newest first by RunAt) ────────────────────────────
        filtered.Sort((a, b) =>
        {
            var ta = a.TryGetProperty("run_at", out var pa) && DateTimeOffset.TryParse(pa.GetString(), out var da) ? da : DateTimeOffset.MinValue;
            var tb = b.TryGetProperty("run_at", out var pb) && DateTimeOffset.TryParse(pb.GetString(), out var db) ? db : DateTimeOffset.MinValue;
            return _historySortOrder == SortOrder.Descending ? tb.CompareTo(ta) : ta.CompareTo(tb);
        });

        // ── Populate grid ────────────────────────────────────────────────────
        _historyGrid.Rows.Clear();
        int rowIdx = 0;
        foreach (var r in filtered)
        {
            string runAt = "";
            if (r.TryGetProperty("run_at", out var rp) &&
                DateTimeOffset.TryParse(rp.GetString(), out var dt))
                runAt = dt.UtcDateTime.ToString("yyyy-MM-dd  HH:mm") + " UTC";

            var ticker    = GetStr(r, "ticker");
            var signal    = GetStr(r, "final_signal");
            var conf      = GetStr(r, "confidence_0_100");
            var sentiment = GetStr(r, "news_sentiment");
            var close     = r.TryGetProperty("last_close",    out var cp) ? $"{cp.GetDouble():F2}" : "";
            var ret7d     = r.TryGetProperty("return_7d_pct", out var rp2) ? $"{rp2.GetDouble():+0.00;-0.00}%" : "";
            var vsSma7    = GetStr(r, "close_vs_sma7");
            var rsi       = r.TryGetProperty("rsi_14",        out var ri) ? $"{ri.GetDouble():F1}" : "";

            _historyGrid.Rows.Add(runAt, ticker, signal.Replace("_", " ").ToUpperInvariant(),
                conf, sentiment, close, ret7d, vsSma7, rsi);

            var row = _historyGrid.Rows[rowIdx];
            row.DefaultCellStyle.BackColor = rowIdx % 2 == 0 ? Color.White : Color.FromArgb(247, 250, 255);

            row.Cells["HSignal"].Style.Font      = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            row.Cells["HSignal"].Style.ForeColor = signal switch
            {
                "high_conviction_up"   => Color.FromArgb(0, 155, 75),
                "likely_up"            => Color.FromArgb(30, 130, 60),
                "high_conviction_down" => Color.FromArgb(180, 0, 0),
                "likely_down"          => Color.FromArgb(200, 40, 40),
                _                      => Color.FromArgb(175, 105, 0),
            };
            rowIdx++;
        }

        // ── Update sort glyph ────────────────────────────────────────────────
        foreach (DataGridViewColumn col in _historyGrid.Columns)
            col.HeaderCell.SortGlyphDirection = SortOrder.None;
        if (_historySortCol < _historyGrid.Columns.Count)
            _historyGrid.Columns[_historySortCol].HeaderCell.SortGlyphDirection = _historySortOrder;

        // ── Update summary bar ───────────────────────────────────────────────
        UpdateHistorySummary(all, filtered);
    }

    private void HistoryGrid_ColumnHeaderClick(object? sender, DataGridViewCellMouseEventArgs e)
    {
        if (e.ColumnIndex == _historySortCol)
            _historySortOrder = _historySortOrder == SortOrder.Ascending
                ? SortOrder.Descending : SortOrder.Ascending;
        else
        {
            _historySortCol   = e.ColumnIndex;
            _historySortOrder = SortOrder.Descending;
        }
        LoadHistoryFromFile(); // re-sort
    }

    private void UpdateHistorySummary(List<JsonElement> all, List<JsonElement> filtered)
    {
        // Aggregate per-ticker signal counts from the filtered set
        var groups = filtered
            .GroupBy(r => GetStr(r, "ticker").ToUpperInvariant())
            .OrderBy(g => g.Key);

        var parts = new List<string>
        {
            $"{filtered.Count} record{(filtered.Count != 1 ? "s" : "")} shown  ({all.Count} total)",
        };

        foreach (var g in groups)
        {
            int up   = g.Count(r => GetStr(r, "final_signal").Contains("up"));
            int down = g.Count(r => GetStr(r, "final_signal").Contains("down"));
            int unc  = g.Count() - up - down;
            parts.Add($"{g.Key}: {g.Count()} ({up}↑ {down}↓ {unc}?)");
        }

        _historySummaryLabel.Text = "  " + string.Join("   |   ", parts);
    }

    private void ExportHistoryToCsv(object? sender, EventArgs e)
    {
        if (_historyGrid.Rows.Count == 0)
        {
            MessageBox.Show("No records to export. Load history first.", "Nothing to Export",
                MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        using var dlg = new SaveFileDialog
        {
            Title    = "Export History to CSV",
            Filter   = "CSV files (*.csv)|*.csv",
            FileName = $"signal_history_{DateTime.Now:yyyyMMdd_HHmm}.csv",
        };
        if (dlg.ShowDialog() != DialogResult.OK) return;

        try
        {
            var sb = new StringBuilder();
            // Header row
            var headers = _historyGrid.Columns.Cast<DataGridViewColumn>()
                .Select(c => $"\"{c.HeaderText}\"");
            sb.AppendLine(string.Join(",", headers));
            // Data rows
            foreach (DataGridViewRow row in _historyGrid.Rows)
            {
                var cells = row.Cells.Cast<DataGridViewCell>()
                    .Select(c => $"\"{(c.Value?.ToString() ?? "").Replace("\"", "\"\"")}\"");
                sb.AppendLine(string.Join(",", cells));
            }
            File.WriteAllText(dlg.FileName, sb.ToString(), Encoding.UTF8);
            SetStatus($"Exported {_historyGrid.Rows.Count} records → {Path.GetFileName(dlg.FileName)}");
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Export failed:\n{ex.Message}", "Export Error",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    // -----------------------------------------------------------------------
    // UI helpers
    // -----------------------------------------------------------------------

    private static Label MakeSettingLabel(string text) => new()
    {
        Text      = text,
        Anchor    = AnchorStyles.Left | AnchorStyles.Right,
        TextAlign = ContentAlignment.MiddleRight,
        Font      = new Font("Segoe UI", 8.5f),
        ForeColor = Color.FromArgb(60, 70, 95),
    };

    private static Button MakeBtn(string text) => new()
    {
        Text      = text,
        Dock      = DockStyle.Fill,
        FlatStyle = FlatStyle.System,
        Font      = new Font("Segoe UI", 8.5f),
    };

    private static Button MakeSmallBtn(string text, int width) => new()
    {
        Text      = text,
        Width     = width,
        Height    = 26,
        FlatStyle = FlatStyle.System,
        Margin    = new Padding(2, 0, 2, 0),
        Font      = new Font("Segoe UI", 8.5f),
    };

    private void SetStatus(string message) =>
        _statusLabel.Text = $"  {message}";

    // -----------------------------------------------------------------------
    // Form overrides
    // -----------------------------------------------------------------------

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _cts?.Cancel();
        base.OnFormClosing(e);
    }
}

// ---------------------------------------------------------------------------
// AddTickerDialog — lightweight inline dialog for manual ticker entry
// ---------------------------------------------------------------------------

internal sealed class AddTickerDialog : Form
{
    public string Ticker { get; private set; } = "";

    private readonly TextBox _box;

    public AddTickerDialog()
    {
        Text            = "Add Ticker";
        Width           = 320;
        Height          = 130;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox     = false;
        MinimizeBox     = false;
        StartPosition   = FormStartPosition.CenterParent;
        BackColor       = Color.FromArgb(248, 249, 252);

        var lbl = new Label
        {
            Text      = "Ticker symbol:",
            Location  = new Point(14, 18),
            AutoSize  = true,
            ForeColor = Color.FromArgb(60, 70, 95),
            Font      = new Font("Segoe UI", 9f),
        };

        _box = new TextBox
        {
            Location          = new Point(14, 40),
            Width             = 190,
            CharacterCasing   = CharacterCasing.Upper,
            PlaceholderText   = "e.g. AAPL",
            Font              = new Font("Consolas", 10f),
        };
        _box.KeyDown += (_, e) => { if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; Confirm(); } };

        var okBtn = new Button
        {
            Text      = "Add",
            Location  = new Point(214, 38),
            Width     = 80,
            Height    = 26,
            Font      = new Font("Segoe UI", 9f, FontStyle.Bold),
            BackColor = Color.FromArgb(0, 115, 207),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Cursor    = Cursors.Hand,
        };
        okBtn.FlatAppearance.BorderSize = 0;
        okBtn.Click += (_, _) => Confirm();

        Controls.AddRange(new Control[] { lbl, _box, okBtn });
        AcceptButton = okBtn;
        ActiveControl = _box;
    }

    private void Confirm()
    {
        var t = _box.Text.Trim().ToUpperInvariant();
        if (string.IsNullOrEmpty(t) || t.Length > 10 || !t.All(c => char.IsLetterOrDigit(c) || c == '.' || c == '-'))
        {
            MessageBox.Show("Enter a valid ticker symbol (1-10 characters, letters/digits/dot/dash).",
                "Invalid Ticker", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        Ticker       = t;
        DialogResult = DialogResult.OK;
        Close();
    }
}
