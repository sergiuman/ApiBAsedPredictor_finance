using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FinanceSignalUI;

public class Form1 : Form
{
    // -----------------------------------------------------------------------
    // Settings
    // -----------------------------------------------------------------------

    private sealed class AppSettings
    {
        [JsonPropertyName("historyFilePath")]
        public string HistoryFilePath { get; set; } = "";

        [JsonPropertyName("pythonExe")]
        public string PythonExe { get; set; } = "python";

        [JsonPropertyName("projectDir")]
        public string ProjectDir { get; set; } = "";
    }

    private AppSettings _settings = new();
    private readonly string _settingsPath =
        Path.Combine(AppContext.BaseDirectory, "settings.json");

    // -----------------------------------------------------------------------
    // Controls
    // -----------------------------------------------------------------------

    private TextBox _historyFileBox = null!;
    private TextBox _pythonExeBox = null!;
    private TextBox _projectDirBox = null!;
    private TextBox _tickerBox = null!;
    private DataGridView _grid = null!;
    private TextBox _reportBox = null!;
    private ToolStripStatusLabel _statusLabel = null!;

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    public Form1()
    {
        Text = "Finance Signal UI";
        Width = 1100;
        Height = 750;
        MinimumSize = new Size(800, 600);
        StartPosition = FormStartPosition.CenterScreen;

        BuildLayout();
        LoadSettings();

        if (string.IsNullOrEmpty(_settings.HistoryFilePath))
            AutoDetectHistoryFile();
    }

    // -----------------------------------------------------------------------
    // Layout
    // -----------------------------------------------------------------------

    private void BuildLayout()
    {
        SuspendLayout();

        // ── Status strip ────────────────────────────────────────────────────
        var statusStrip = new StatusStrip { Dock = DockStyle.Bottom };
        _statusLabel = new ToolStripStatusLabel("Ready") { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
        statusStrip.Items.Add(_statusLabel);

        // ── Settings group box ───────────────────────────────────────────────
        var settingsGroup = new GroupBox
        {
            Text = "Settings",
            Dock = DockStyle.Top,
            Height = 115,
            Padding = new Padding(8, 4, 8, 4),
        };

        var settingsPanel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 3,
            RowCount = 3,
        };
        settingsPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100));
        settingsPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        settingsPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        settingsPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 33));
        settingsPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 33));
        settingsPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 34));

        // Row 0: History file
        settingsPanel.Controls.Add(new Label { Text = "History File:", Anchor = AnchorStyles.Left | AnchorStyles.Right, TextAlign = ContentAlignment.MiddleRight }, 0, 0);
        _historyFileBox = new TextBox { Dock = DockStyle.Fill, Anchor = AnchorStyles.Left | AnchorStyles.Right };
        _historyFileBox.TextChanged += (_, _) => { _settings.HistoryFilePath = _historyFileBox.Text; SaveSettings(); };
        settingsPanel.Controls.Add(_historyFileBox, 1, 0);
        var browseHistoryBtn = new Button { Text = "Browse...", Dock = DockStyle.Fill };
        browseHistoryBtn.Click += BrowseHistoryFile;
        settingsPanel.Controls.Add(browseHistoryBtn, 2, 0);

        // Row 1: Python exe
        settingsPanel.Controls.Add(new Label { Text = "Python Exe:", Anchor = AnchorStyles.Left | AnchorStyles.Right, TextAlign = ContentAlignment.MiddleRight }, 0, 1);
        _pythonExeBox = new TextBox { Dock = DockStyle.Fill };
        _pythonExeBox.TextChanged += (_, _) => { _settings.PythonExe = _pythonExeBox.Text; SaveSettings(); };
        settingsPanel.Controls.Add(_pythonExeBox, 1, 1);
        settingsPanel.Controls.Add(new Panel(), 2, 1); // spacer

        // Row 2: Project dir
        settingsPanel.Controls.Add(new Label { Text = "Project Dir:", Anchor = AnchorStyles.Left | AnchorStyles.Right, TextAlign = ContentAlignment.MiddleRight }, 0, 2);
        _projectDirBox = new TextBox { Dock = DockStyle.Fill };
        _projectDirBox.TextChanged += (_, _) => { _settings.ProjectDir = _projectDirBox.Text; SaveSettings(); };
        settingsPanel.Controls.Add(_projectDirBox, 1, 2);
        var browseProjectBtn = new Button { Text = "Browse...", Dock = DockStyle.Fill };
        browseProjectBtn.Click += BrowseProjectDir;
        settingsPanel.Controls.Add(browseProjectBtn, 2, 2);

        settingsGroup.Controls.Add(settingsPanel);

        // ── Ticker row ───────────────────────────────────────────────────────
        var tickerPanel = new Panel
        {
            Dock = DockStyle.Top,
            Height = 42,
            Padding = new Padding(8, 6, 8, 6),
        };

        var tickerLabel = new Label
        {
            Text = "Ticker:",
            Width = 50,
            TextAlign = ContentAlignment.MiddleLeft,
            Location = new Point(8, 10),
        };
        _tickerBox = new TextBox
        {
            Width = 80,
            CharacterCasing = CharacterCasing.Upper,
            Location = new Point(62, 8),
        };
        _tickerBox.KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; LoadHistory(); }
        };

        var loadBtn = new Button { Text = "Load History", Location = new Point(150, 7), Width = 100 };
        loadBtn.Click += (_, _) => LoadHistory();

        var runBtn = new Button { Text = "Run Analysis", Location = new Point(258, 7), Width = 100 };
        runBtn.Click += (_, _) => RunAnalysis();

        tickerPanel.Controls.AddRange(new Control[] { tickerLabel, _tickerBox, loadBtn, runBtn });

        // ── Split container ──────────────────────────────────────────────────
        var split = new SplitContainer
        {
            Dock = DockStyle.Fill,
            Orientation = Orientation.Horizontal,
            SplitterDistance = 300,
        };

        // Top: DataGridView
        _grid = new DataGridView
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            AllowUserToAddRows = false,
            AllowUserToDeleteRows = false,
            AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
            SelectionMode = DataGridViewSelectionMode.FullRowSelect,
            RowHeadersVisible = false,
            BackgroundColor = SystemColors.Window,
            BorderStyle = BorderStyle.None,
        };
        _grid.Columns.AddRange(
            new DataGridViewTextBoxColumn { Name = "Date",       HeaderText = "Date",        FillWeight = 80 },
            new DataGridViewTextBoxColumn { Name = "TimeUTC",    HeaderText = "Time (UTC)",   FillWeight = 75 },
            new DataGridViewTextBoxColumn { Name = "Signal",     HeaderText = "Signal",       FillWeight = 130 },
            new DataGridViewTextBoxColumn { Name = "Confidence", HeaderText = "Confidence",   FillWeight = 65 },
            new DataGridViewTextBoxColumn { Name = "Sentiment",  HeaderText = "Sentiment",    FillWeight = 75 },
            new DataGridViewTextBoxColumn { Name = "Close",      HeaderText = "Close ($)",    FillWeight = 70 },
            new DataGridViewTextBoxColumn { Name = "Return7d",   HeaderText = "7d Return %",  FillWeight = 75 },
            new DataGridViewTextBoxColumn { Name = "VsSMA7",     HeaderText = "vs SMA7",      FillWeight = 65 },
            new DataGridViewTextBoxColumn { Name = "RSI14",      HeaderText = "RSI-14",       FillWeight = 55 }
        );
        split.Panel1.Controls.Add(_grid);

        // Bottom: Report textbox
        _reportBox = new TextBox
        {
            Dock = DockStyle.Fill,
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Both,
            WordWrap = false,
            Font = new Font("Consolas", 9f),
            BackColor = Color.FromArgb(30, 30, 30),
            ForeColor = Color.LightGreen,
        };
        split.Panel2.Controls.Add(_reportBox);

        // ── Assemble (order matters for DockStyle.Top stacking) ──────────────
        Controls.Add(split);
        Controls.Add(tickerPanel);
        Controls.Add(settingsGroup);
        Controls.Add(statusStrip);

        ResumeLayout(false);
        PerformLayout();
    }

    // -----------------------------------------------------------------------
    // Settings persistence
    // -----------------------------------------------------------------------

    private void LoadSettings()
    {
        try
        {
            if (File.Exists(_settingsPath))
            {
                var json = File.ReadAllText(_settingsPath);
                _settings = JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
            }
        }
        catch { /* use defaults */ }

        _historyFileBox.Text = _settings.HistoryFilePath;
        _pythonExeBox.Text   = string.IsNullOrEmpty(_settings.PythonExe) ? "python" : _settings.PythonExe;
        _projectDirBox.Text  = _settings.ProjectDir;
    }

    private void SaveSettings()
    {
        try
        {
            var json = JsonSerializer.Serialize(_settings, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(_settingsPath, json);
        }
        catch { /* swallow */ }
    }

    // -----------------------------------------------------------------------
    // Auto-detect
    // -----------------------------------------------------------------------

    private void AutoDetectHistoryFile()
    {
        // Walk up from the exe directory looking for data/signal_history.jsonl
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
                SaveSettings();
                SetStatus($"Auto-detected history: {candidate}");
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
            SaveSettings();
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
            SaveSettings();
        }
    }

    // -----------------------------------------------------------------------
    // Load History
    // -----------------------------------------------------------------------

    private void LoadHistory()
    {
        var ticker = _tickerBox.Text.Trim().ToUpperInvariant();
        if (string.IsNullOrEmpty(ticker))
        {
            SetStatus("Enter a ticker symbol first.");
            return;
        }

        var path = _historyFileBox.Text.Trim();
        if (!File.Exists(path))
        {
            SetStatus($"History file not found: {path}");
            return;
        }

        try
        {
            var records = ReadHistory(path, ticker);
            PopulateGrid(records);
            SetStatus($"Loaded {records.Count} record(s) for {ticker}.");
        }
        catch (Exception ex)
        {
            SetStatus($"Error reading history: {ex.Message}");
        }
    }

    private static List<JsonElement> ReadHistory(string path, string ticker)
    {
        var results = new List<JsonElement>();
        foreach (var line in File.ReadLines(path, Encoding.UTF8))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed)) continue;
            try
            {
                var doc = JsonDocument.Parse(trimmed);
                if (doc.RootElement.TryGetProperty("ticker", out var tickerProp) &&
                    tickerProp.GetString()?.Equals(ticker, StringComparison.OrdinalIgnoreCase) == true)
                {
                    results.Add(doc.RootElement.Clone());
                }
            }
            catch { /* skip malformed lines */ }
        }
        results.Reverse(); // newest first
        return results;
    }

    private void PopulateGrid(List<JsonElement> records)
    {
        _grid.Rows.Clear();
        foreach (var r in records)
        {
            string date = "", time = "";
            if (r.TryGetProperty("run_at", out var runAtProp) &&
                DateTime.TryParse(runAtProp.GetString(), out var dt))
            {
                var utc = dt.ToUniversalTime();
                date = utc.ToString("yyyy-MM-dd");
                time = utc.ToString("HH:mm:ss");
            }

            var signal    = GetStr(r, "final_signal");
            var conf      = GetStr(r, "confidence_0_100");
            var sentiment = GetStr(r, "news_sentiment");
            var close     = r.TryGetProperty("last_close", out var cp) ? $"{cp.GetDouble():F2}" : "";
            var ret7d     = r.TryGetProperty("return_7d_pct", out var rp) ? $"{rp.GetDouble():+0.00;-0.00}%" : "";
            var vsSma7    = GetStr(r, "close_vs_sma7");
            var rsi14     = r.TryGetProperty("rsi_14", out var ri) ? $"{ri.GetDouble():F1}" : "";

            var signalLabel = signal.Replace("_", " ").ToUpperInvariant();

            _grid.Rows.Add(date, time, signalLabel, conf, sentiment, close, ret7d, vsSma7, rsi14);

            // Colour code the signal cell
            var row = _grid.Rows[_grid.Rows.Count - 1];
            row.Cells["Signal"].Style.ForeColor = signal switch
            {
                "high_conviction_up"   => Color.DarkGreen,
                "likely_up"            => Color.Green,
                "high_conviction_down" => Color.DarkRed,
                "likely_down"          => Color.Red,
                _                      => Color.DarkOrange,
            };
        }
    }

    private static string GetStr(JsonElement el, string key) =>
        el.TryGetProperty(key, out var p) ? p.ToString() : "";

    // -----------------------------------------------------------------------
    // Run Analysis
    // -----------------------------------------------------------------------

    private void RunAnalysis()
    {
        var ticker = _tickerBox.Text.Trim().ToUpperInvariant();
        if (string.IsNullOrEmpty(ticker))
        {
            SetStatus("Enter a ticker symbol first.");
            return;
        }

        var pythonExe  = _pythonExeBox.Text.Trim();
        var projectDir = _projectDirBox.Text.Trim();

        if (string.IsNullOrEmpty(projectDir) || !Directory.Exists(projectDir))
        {
            SetStatus("Set a valid Project Dir in Settings first.");
            return;
        }

        _reportBox.Text = $"Running analysis for {ticker}...\r\n";
        SetStatus($"Running analysis for {ticker}...");

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

        Task.Run(async () =>
        {
            try
            {
                using var proc = new Process { StartInfo = psi };
                var output = new StringBuilder();
                proc.OutputDataReceived += (_, e) => { if (e.Data != null) output.AppendLine(e.Data); };
                proc.ErrorDataReceived  += (_, e) => { if (e.Data != null) output.AppendLine("[ERR] " + e.Data); };

                proc.Start();
                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                await proc.WaitForExitAsync();

                var text = output.ToString();
                Invoke(() =>
                {
                    _reportBox.Text = text;
                    SetStatus(proc.ExitCode == 0
                        ? $"Analysis complete for {ticker}."
                        : $"Analysis finished with exit code {proc.ExitCode}.");
                    LoadHistory(); // auto-reload grid
                });
            }
            catch (Exception ex)
            {
                Invoke(() =>
                {
                    _reportBox.Text = $"Failed to start process:\r\n{ex.Message}";
                    SetStatus("Error running analysis.");
                });
            }
        });
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    private void SetStatus(string message) =>
        _statusLabel.Text = message;
}
