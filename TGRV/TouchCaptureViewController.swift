import UIKit
import Network

protocol TouchCaptureViewDelegate: AnyObject {
    func captureView(_ view: TouchCaptureSurfaceView, didReceive touches: Set<UITouch>, phase: TouchPhase, event: UIEvent?)
}

final class TouchCaptureViewController: UIViewController, TouchCaptureViewDelegate {
    private let captureSurfaceView = TouchCaptureSurfaceView()
    private let hudOverlayView = UIView()
    private let topBarView = UIView()
    private let debugPanelOverlayView = UIView()

    private let statusLabel = UILabel()
    private let telemetryHostField = UITextField()
    private let telemetryPortField = UITextField()
    private let telemetryWarningLabel = UILabel()
    private let telemetryHelperLabel = UILabel()
    private let telemetryDiagnosticsHeaderLabel = UILabel()
    private let telemetryTargetLabel = UILabel()
    private let telemetryHostValueLabel = UILabel()
    private let telemetryPortValueLabel = UILabel()
    private let telemetryStateLabel = UILabel()
    private let telemetryErrorLabel = UILabel()
    private let telemetryStatsLabel = UILabel()
    private let telemetryStatusLabel = UILabel()
    private let telemetryDetailLabel = UILabel()
    private let telemetryWifiLabel = UILabel()
    private let telemetryFixLabel = UILabel()
    private let telemetryPermissionLabel = UILabel()
    private let telemetryConnectionTestResultLabel = UILabel()

    private var connectButton: UIButton?
    private var disconnectButton: UIButton?
    private var saveButton: UIButton?
    private var connectionTestButton: UIButton?
    private var debugToggleButton: UIButton?
    private var telemetryTimer: Timer?
    private let pathMonitor = NWPathMonitor()
    private let pathMonitorQueue = DispatchQueue(label: "com.gazza.tgrv.path-monitor")
    private var currentPathStatus: NWPath.Status = .requiresConnection
    private var usesWiFi = false
    private var isDebugPanelVisible = false

    override func loadView() {
        view = UIView()
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        overrideUserInterfaceStyle = .dark
        view.backgroundColor = .black

        configureHierarchy()
        configureTopBar()
        configureDebugPanel()
        configureTelemetryState()

        if TouchLogger.shared.telemetryConfiguration().shouldAutoConnect {
            TouchLogger.shared.startLiveTelemetrySession()
        }

        let doubleTapRecognizer = UITapGestureRecognizer(target: self, action: #selector(handleDoubleTap))
        doubleTapRecognizer.numberOfTapsRequired = 2
        doubleTapRecognizer.cancelsTouchesInView = false
        captureSurfaceView.addGestureRecognizer(doubleTapRecognizer)

        pathMonitor.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                self?.currentPathStatus = path.status
                self?.usesWiFi = path.usesInterfaceType(.wifi)
                self?.refreshTelemetryStatus()
            }
        }
        pathMonitor.start(queue: pathMonitorQueue)

        telemetryTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.refreshTelemetryStatus()
        }

        refreshTelemetryStatus()
        view.setNeedsLayout()
    }

    deinit {
        telemetryTimer?.invalidate()
        pathMonitor.cancel()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        view.bringSubviewToFront(hudOverlayView)
        view.bringSubviewToFront(topBarView)
        if isDebugPanelVisible {
            view.bringSubviewToFront(debugPanelOverlayView)
        }
    }

    func captureView(_ view: TouchCaptureSurfaceView, didReceive touches: Set<UITouch>, phase: TouchPhase, event: UIEvent?) {
        let totalEvents = TouchLogger.shared.recordTouches(touches, phase: phase, in: view, event: event)
        statusLabel.text = statusHUDText(eventCountOverride: totalEvents)
        refreshTelemetryStatus()
    }

    @objc private func handleDoubleTap() {
        TouchLogger.shared.resetSession()
        statusLabel.text = statusHUDText(eventCountOverride: 0)
        refreshTelemetryStatus()
    }

    @objc private func exportSession() {
        do {
            let fileURL = try TouchLogger.shared.exportCurrentSession()
            let alert = UIAlertController(
                title: "Exported",
                message: fileURL.path,
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
        } catch {
            let alert = UIAlertController(
                title: "Export Failed",
                message: error.localizedDescription,
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
        }
    }

    @objc private func toggleDebugPanel() {
        print("Debug button tapped")
        setDebugPanelVisible(!isDebugPanelVisible)
    }

    @objc private func closeDebugPanel() {
        setDebugPanelVisible(false)
    }

    @objc private func connectTelemetry() {
        let host = normalizedHostText()
        let portValue = normalizedPortValue()
        guard !host.isEmpty else {
            TouchLogger.shared.updateTelemetryConfiguration(host: "", port: portValue, connect: false)
            refreshTelemetryStatus()
            return
        }
        TouchLogger.shared.updateTelemetryConfiguration(host: host, port: portValue, connect: false)
        TouchLogger.shared.connectLiveTelemetry()
        TouchLogger.shared.startLiveTelemetrySession()
        refreshTelemetryStatus()
    }

    @objc private func disconnectTelemetry() {
        TouchLogger.shared.disconnectLiveTelemetry()
        refreshTelemetryStatus()
    }

    @objc private func saveTelemetrySettings() {
        let host = normalizedHostText()
        let portValue = normalizedPortValue()
        TouchLogger.shared.updateTelemetryConfiguration(host: host, port: portValue, connect: false)
        if host.isEmpty {
            TouchLogger.shared.disconnectLiveTelemetry()
        }
        refreshTelemetryStatus()
    }

    @objc private func runConnectionTest() {
        let host = normalizedHostText()
        let portValue = normalizedPortValue()
        guard !host.isEmpty else {
            telemetryConnectionTestResultLabel.text = "Connection test failed: host is empty."
            refreshTelemetryStatus()
            return
        }

        TouchLogger.shared.updateTelemetryConfiguration(host: host, port: portValue, connect: false)
        telemetryConnectionTestResultLabel.text = "Running connection test…"
        TouchLogger.shared.runTelemetryConnectionTest { [weak self] result in
            guard let self else { return }
            self.telemetryConnectionTestResultLabel.text = "\(result.status.rawValue): \(result.message)\n\(result.suggestion)"
            self.refreshTelemetryStatus()
        }
    }

    @objc private func telemetryFieldChanged() {
        refreshTelemetryStatus()
    }

    private func configureHierarchy() {
        captureSurfaceView.translatesAutoresizingMaskIntoConstraints = false
        captureSurfaceView.captureDelegate = self
        view.addSubview(captureSurfaceView)

        hudOverlayView.translatesAutoresizingMaskIntoConstraints = false
        hudOverlayView.backgroundColor = .clear
        hudOverlayView.isUserInteractionEnabled = false
        view.addSubview(hudOverlayView)

        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.textColor = .white
        statusLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        statusLabel.numberOfLines = 1
        statusLabel.textAlignment = .left
        statusLabel.backgroundColor = UIColor(white: 0.0, alpha: 0.45)
        statusLabel.layer.cornerRadius = 8
        statusLabel.layer.masksToBounds = true
        hudOverlayView.addSubview(statusLabel)

        topBarView.translatesAutoresizingMaskIntoConstraints = false
        topBarView.backgroundColor = UIColor(white: 0.0, alpha: 0.72)
        topBarView.layer.cornerRadius = 10
        topBarView.clipsToBounds = true
        view.addSubview(topBarView)

        debugPanelOverlayView.translatesAutoresizingMaskIntoConstraints = false
        debugPanelOverlayView.backgroundColor = UIColor(white: 0.08, alpha: 0.98)
        debugPanelOverlayView.layer.cornerRadius = 12
        debugPanelOverlayView.layer.shadowColor = UIColor.black.cgColor
        debugPanelOverlayView.layer.shadowOpacity = 0.35
        debugPanelOverlayView.layer.shadowRadius = 14
        debugPanelOverlayView.layer.shadowOffset = CGSize(width: -2, height: 0)
        debugPanelOverlayView.isHidden = true
        debugPanelOverlayView.alpha = 0
        debugPanelOverlayView.clipsToBounds = false
        debugPanelOverlayView.isUserInteractionEnabled = true
        view.addSubview(debugPanelOverlayView)

        NSLayoutConstraint.activate([
            captureSurfaceView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            captureSurfaceView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            captureSurfaceView.topAnchor.constraint(equalTo: view.topAnchor),
            captureSurfaceView.bottomAnchor.constraint(equalTo: view.bottomAnchor),

            hudOverlayView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 12),
            hudOverlayView.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -12),

            statusLabel.leadingAnchor.constraint(equalTo: hudOverlayView.leadingAnchor),
            statusLabel.trailingAnchor.constraint(equalTo: hudOverlayView.trailingAnchor),
            statusLabel.topAnchor.constraint(equalTo: hudOverlayView.topAnchor),
            statusLabel.bottomAnchor.constraint(equalTo: hudOverlayView.bottomAnchor),

            topBarView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 10),
            topBarView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -10),
            topBarView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 8),
            topBarView.heightAnchor.constraint(equalToConstant: 44),

            debugPanelOverlayView.topAnchor.constraint(equalTo: topBarView.bottomAnchor, constant: 8),
            debugPanelOverlayView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -8),
            debugPanelOverlayView.widthAnchor.constraint(equalToConstant: 340),
            debugPanelOverlayView.bottomAnchor.constraint(lessThanOrEqualTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -8),
        ])
    }

    private func configureTopBar() {
        let titleLabel = UILabel()
        titleLabel.text = "Touchprint Logger"
        titleLabel.textColor = .white
        titleLabel.font = .systemFont(ofSize: 13, weight: .semibold)

        let titleContainer = UIView()
        titleContainer.translatesAutoresizingMaskIntoConstraints = false
        titleContainer.addSubview(titleLabel)
        titleLabel.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            titleLabel.leadingAnchor.constraint(equalTo: titleContainer.leadingAnchor, constant: 12),
            titleLabel.centerYAnchor.constraint(equalTo: titleContainer.centerYAnchor),
        ])

        let exportButton = UIButton(type: .system)
        exportButton.setTitle("Export", for: .normal)
        exportButton.addTarget(self, action: #selector(exportSession), for: .touchUpInside)

        let debugButton = UIButton(type: .system)
        debugButton.setTitle("Debug", for: .normal)
        debugButton.addTarget(self, action: #selector(toggleDebugPanel), for: .touchUpInside)
        debugButton.isUserInteractionEnabled = true
        self.debugToggleButton = debugButton

        let buttonsRow = UIStackView(arrangedSubviews: [exportButton, debugButton])
        buttonsRow.axis = .horizontal
        buttonsRow.spacing = 10
        buttonsRow.alignment = .center
        buttonsRow.translatesAutoresizingMaskIntoConstraints = false

        topBarView.addSubview(titleContainer)
        topBarView.addSubview(buttonsRow)

        NSLayoutConstraint.activate([
            titleContainer.leadingAnchor.constraint(equalTo: topBarView.leadingAnchor),
            titleContainer.topAnchor.constraint(equalTo: topBarView.topAnchor),
            titleContainer.bottomAnchor.constraint(equalTo: topBarView.bottomAnchor),
            titleContainer.widthAnchor.constraint(greaterThanOrEqualToConstant: 160),

            buttonsRow.trailingAnchor.constraint(equalTo: topBarView.trailingAnchor, constant: -12),
            buttonsRow.centerYAnchor.constraint(equalTo: topBarView.centerYAnchor),
        ])
    }

    private func configureDebugPanel() {
        let scrollView = UIScrollView()
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.alwaysBounceVertical = true
        scrollView.showsVerticalScrollIndicator = true
        scrollView.backgroundColor = .clear
        debugPanelOverlayView.addSubview(scrollView)

        let contentStack = UIStackView()
        contentStack.translatesAutoresizingMaskIntoConstraints = false
        contentStack.axis = .vertical
        contentStack.spacing = 8
        contentStack.isLayoutMarginsRelativeArrangement = true
        contentStack.layoutMargins = UIEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        scrollView.addSubview(contentStack)

        NSLayoutConstraint.activate([
            scrollView.leadingAnchor.constraint(equalTo: debugPanelOverlayView.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: debugPanelOverlayView.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: debugPanelOverlayView.topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: debugPanelOverlayView.bottomAnchor),

            contentStack.leadingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.leadingAnchor),
            contentStack.trailingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.trailingAnchor),
            contentStack.topAnchor.constraint(equalTo: scrollView.contentLayoutGuide.topAnchor),
            contentStack.bottomAnchor.constraint(equalTo: scrollView.contentLayoutGuide.bottomAnchor),
            contentStack.widthAnchor.constraint(equalTo: scrollView.frameLayoutGuide.widthAnchor),
        ])

        let headerRow = UIStackView()
        headerRow.axis = .horizontal
        headerRow.spacing = 8
        headerRow.alignment = .center

        let titleLabel = UILabel()
        titleLabel.text = "Debug / Telemetry"
        titleLabel.textColor = .white
        titleLabel.font = .systemFont(ofSize: 13, weight: .semibold)

        let spacer = UIView()
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)

        let closeButton = UIButton(type: .system)
        closeButton.setTitle("Close", for: .normal)
        closeButton.addTarget(self, action: #selector(closeDebugPanel), for: .touchUpInside)
        closeButton.isUserInteractionEnabled = true

        headerRow.addArrangedSubview(titleLabel)
        headerRow.addArrangedSubview(spacer)
        headerRow.addArrangedSubview(closeButton)

        telemetryHostField.translatesAutoresizingMaskIntoConstraints = false
        telemetryHostField.borderStyle = .roundedRect
        telemetryHostField.autocapitalizationType = .none
        telemetryHostField.autocorrectionType = .no
        telemetryHostField.textContentType = .URL
        telemetryHostField.placeholder = "Mac LAN IP or 127.0.0.1 (simulator)"
        telemetryHostField.text = TouchLogger.shared.telemetryConfiguration().host
        telemetryHostField.addTarget(self, action: #selector(telemetryFieldChanged), for: .editingChanged)
        telemetryHostField.isUserInteractionEnabled = true

        telemetryPortField.translatesAutoresizingMaskIntoConstraints = false
        telemetryPortField.borderStyle = .roundedRect
        telemetryPortField.keyboardType = .numberPad
        telemetryPortField.text = "\(TouchLogger.shared.telemetryConfiguration().port)"
        telemetryPortField.addTarget(self, action: #selector(telemetryFieldChanged), for: .editingChanged)
        telemetryPortField.isUserInteractionEnabled = true

        telemetryWarningLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryWarningLabel.textColor = .systemYellow
        telemetryWarningLabel.font = .systemFont(ofSize: 11)
        telemetryWarningLabel.numberOfLines = 0

        telemetryHelperLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryHelperLabel.textColor = .systemGray
        telemetryHelperLabel.font = .systemFont(ofSize: 11)
        telemetryHelperLabel.numberOfLines = 0

        telemetryDiagnosticsHeaderLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryDiagnosticsHeaderLabel.textColor = .white
        telemetryDiagnosticsHeaderLabel.font = .systemFont(ofSize: 12, weight: .semibold)
        telemetryDiagnosticsHeaderLabel.text = "Network Diagnostics"

        telemetryTargetLabel.textColor = .systemGray
        telemetryTargetLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryTargetLabel.numberOfLines = 0
        telemetryHostValueLabel.textColor = .systemGray
        telemetryHostValueLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryHostValueLabel.numberOfLines = 0
        telemetryPortValueLabel.textColor = .systemGray
        telemetryPortValueLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryPortValueLabel.numberOfLines = 0
        telemetryStateLabel.textColor = .systemGray
        telemetryStateLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryStateLabel.numberOfLines = 0
        telemetryStatusLabel.textColor = .systemGreen
        telemetryStatusLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryStatusLabel.numberOfLines = 0
        telemetryErrorLabel.textColor = .systemOrange
        telemetryErrorLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryErrorLabel.numberOfLines = 0
        telemetryDetailLabel.textColor = .systemGray
        telemetryDetailLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryDetailLabel.numberOfLines = 0
        telemetryStatsLabel.textColor = .systemGray
        telemetryStatsLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryStatsLabel.numberOfLines = 0
        telemetryWifiLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryWifiLabel.textColor = .systemGray
        telemetryWifiLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryWifiLabel.numberOfLines = 0
        telemetryFixLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryFixLabel.textColor = .systemYellow
        telemetryFixLabel.font = .systemFont(ofSize: 11)
        telemetryFixLabel.numberOfLines = 0
        telemetryPermissionLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryPermissionLabel.textColor = .systemGray
        telemetryPermissionLabel.font = .systemFont(ofSize: 11)
        telemetryPermissionLabel.numberOfLines = 0
        telemetryPermissionLabel.text = testPromptText(for: TouchLogger.shared.telemetryConfiguration().host)
        telemetryConnectionTestResultLabel.translatesAutoresizingMaskIntoConstraints = false
        telemetryConnectionTestResultLabel.textColor = .systemOrange
        telemetryConnectionTestResultLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        telemetryConnectionTestResultLabel.numberOfLines = 0
        telemetryConnectionTestResultLabel.text = "Connection test not run yet."

        let settingsHeader = UILabel.makeCaption("Settings")
        let diagnosticsHeader = UILabel.makeCaption("Diagnostics")

        let hostRow = makeFieldRow(label: "Telemetry Host", field: telemetryHostField)
        let portRow = makeFieldRow(label: "Telemetry Port", field: telemetryPortField)
        let buttonsRow = makeButtonsRow()

        contentStack.addArrangedSubview(headerRow)
        contentStack.addArrangedSubview(telemetryWarningLabel)
        contentStack.addArrangedSubview(telemetryHelperLabel)
        contentStack.addArrangedSubview(telemetryPermissionLabel)
        contentStack.addArrangedSubview(settingsHeader)
        contentStack.addArrangedSubview(hostRow)
        contentStack.addArrangedSubview(portRow)
        contentStack.addArrangedSubview(buttonsRow)
        contentStack.addArrangedSubview(diagnosticsHeader)
        contentStack.addArrangedSubview(telemetryTargetLabel)
        contentStack.addArrangedSubview(telemetryHostValueLabel)
        contentStack.addArrangedSubview(telemetryPortValueLabel)
        contentStack.addArrangedSubview(telemetryStateLabel)
        contentStack.addArrangedSubview(telemetryStatusLabel)
        contentStack.addArrangedSubview(telemetryErrorLabel)
        contentStack.addArrangedSubview(telemetryDetailLabel)
        contentStack.addArrangedSubview(telemetryStatsLabel)
        contentStack.addArrangedSubview(telemetryWifiLabel)
        contentStack.addArrangedSubview(telemetryFixLabel)
        contentStack.addArrangedSubview(telemetryConnectionTestResultLabel)
    }

    private func configureTelemetryState() {
        telemetryWarningLabel.textColor = .systemYellow
        telemetryHelperLabel.text = helperTelemetryText()
        telemetryConnectionTestResultLabel.text = "Connection test not run yet."
        refreshTelemetryStatus()
    }

    private func makeFieldRow(label: String, field: UITextField) -> UIStackView {
        let row = UIStackView(arrangedSubviews: [UILabel.makeCaption(label), field])
        row.axis = .horizontal
        row.spacing = 8
        row.alignment = .center
        return row
    }

    private func makeButtonsRow() -> UIStackView {
        let connectButton = UIButton(type: .system)
        connectButton.setTitle("Connect", for: .normal)
        connectButton.addTarget(self, action: #selector(connectTelemetry), for: .touchUpInside)
        connectButton.isUserInteractionEnabled = true

        let disconnectButton = UIButton(type: .system)
        disconnectButton.setTitle("Disconnect", for: .normal)
        disconnectButton.addTarget(self, action: #selector(disconnectTelemetry), for: .touchUpInside)
        disconnectButton.isUserInteractionEnabled = true

        let saveButton = UIButton(type: .system)
        saveButton.setTitle("Save Settings", for: .normal)
        saveButton.addTarget(self, action: #selector(saveTelemetrySettings), for: .touchUpInside)
        saveButton.isUserInteractionEnabled = true

        let testButton = UIButton(type: .system)
        testButton.setTitle("Run Connection Test", for: .normal)
        testButton.addTarget(self, action: #selector(runConnectionTest), for: .touchUpInside)
        testButton.isUserInteractionEnabled = true

        self.connectButton = connectButton
        self.disconnectButton = disconnectButton
        self.saveButton = saveButton
        self.connectionTestButton = testButton

        let row = UIStackView(arrangedSubviews: [connectButton, disconnectButton, saveButton, testButton])
        row.axis = .vertical
        row.spacing = 6
        return row
    }

    private func setDebugPanelVisible(_ visible: Bool) {
        guard visible != isDebugPanelVisible else { return }
        isDebugPanelVisible = visible
        if visible {
            debugPanelOverlayView.isHidden = false
            debugPanelOverlayView.alpha = 1.0
            view.bringSubviewToFront(debugPanelOverlayView)
            view.bringSubviewToFront(topBarView)
            view.bringSubviewToFront(hudOverlayView)
        } else {
            debugPanelOverlayView.alpha = 0
            debugPanelOverlayView.isHidden = true
        }
    }

    private func refreshTelemetryStatus() {
        let snapshot = TouchLogger.shared.liveTelemetrySnapshot()
        let currentHost = normalizedHostText()
        let currentPort = normalizedPortValue()
        statusLabel.text = statusHUDText(snapshot: snapshot)

        telemetryTargetLabel.text = "Target \(targetText(host: currentHost, port: currentPort))"
        telemetryHostValueLabel.text = "Target Host \(currentHost.isEmpty ? "required" : currentHost)"
        telemetryPortValueLabel.text = "Target Port \(currentPort)"
        telemetryStateLabel.text = "Connection State \(snapshot.connectionState.rawValue)"
        telemetryStatusLabel.text = "Events Sent \(snapshot.eventsSent) • Buffered \(snapshot.bufferedMessages)"
        telemetryErrorLabel.text = "Last Error \(snapshot.lastError ?? "none")"
        telemetryDetailLabel.text = "Current Session \(snapshot.currentSessionId ?? SessionManager.shared.currentSessionId().uuidString)"
        telemetryStatsLabel.text = "Target \(targetText(host: currentHost, port: currentPort))"
        telemetryWarningLabel.isHidden = !shouldShowTelemetryWarning(for: currentHost)
        telemetryWarningLabel.text = telemetryWarningText(for: currentHost)
        telemetryHelperLabel.text = helperTelemetryText()
        telemetryPermissionLabel.text = testPromptText(for: currentHost)
        telemetryWifiLabel.text = wifiStatusText()
        telemetryFixLabel.text = suggestedFixText(snapshot: snapshot, host: currentHost, port: currentPort)

        if !telemetryHostField.isEditing && telemetryHostField.text != currentHost {
            telemetryHostField.text = currentHost
        }
        if !telemetryPortField.isEditing && telemetryPortField.text != "\(currentPort)" {
            telemetryPortField.text = "\(currentPort)"
        }

        updateTelemetryButtonState(host: currentHost)
        view.bringSubviewToFront(hudOverlayView)
        view.bringSubviewToFront(topBarView)
        if isDebugPanelVisible {
            view.bringSubviewToFront(debugPanelOverlayView)
        }
    }

    private func normalizedHostText() -> String {
        telemetryHostField.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private func normalizedPortValue() -> UInt16 {
        UInt16(telemetryPortField.text ?? "") ?? 8765
    }

    private func statusHUDText(snapshot: LiveTelemetrySnapshot? = nil, eventCountOverride: Int? = nil) -> String {
        let currentSnapshot = snapshot ?? TouchLogger.shared.liveTelemetrySnapshot()
        let events = eventCountOverride ?? TouchLogger.shared.eventCount()
        return "Session: \(shortSessionId(SessionManager.shared.currentSessionId()))  Events: \(events)  Live: \(currentSnapshot.connectionState.rawValue)"
    }

    private func shortSessionId(_ sessionId: UUID) -> String {
        let value = sessionId.uuidString
        guard value.count > 8 else { return value }
        return "\(value.prefix(4))…\(value.suffix(4))"
    }

    private func helperTelemetryText() -> String {
        #if targetEnvironment(simulator)
        return "Simulator may use 127.0.0.1. Real devices must use the Mac LAN IP shown in Touchprint Analyzer."
        #else
        return "Use the Mac LAN IP shown in Touchprint Analyzer."
        #endif
    }

    private func targetText(host: String, port: UInt16) -> String {
        let targetHost = host.isEmpty ? "host required" : host
        return "\(targetHost):\(port)"
    }

    private func updateTelemetryButtonState(host: String) {
        let hasHost = !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        connectButton?.isEnabled = hasHost
        connectButton?.alpha = hasHost ? 1.0 : 0.4
        disconnectButton?.isEnabled = true
        disconnectButton?.alpha = 1.0
        saveButton?.isEnabled = true
        saveButton?.alpha = 1.0
        connectionTestButton?.isEnabled = hasHost
        connectionTestButton?.alpha = hasHost ? 1.0 : 0.4
    }

    private func wifiStatusText() -> String {
        switch currentPathStatus {
        case .satisfied:
            return usesWiFi ? "Wi-Fi status: connected" : "Network status: connected"
        case .unsatisfied:
            return "Wi-Fi status: unavailable or blocked"
        case .requiresConnection:
            return "Wi-Fi status: waiting for connection"
        @unknown default:
            return "Wi-Fi status: unknown"
        }
    }

    private func suggestedFixText(snapshot: LiveTelemetrySnapshot, host: String, port: UInt16) -> String {
        if host.isEmpty {
            return "Enter the Mac LAN IP shown in Touchprint Analyzer."
        }
        if host == "127.0.0.1" || host == "localhost" || host == "::1" {
            #if targetEnvironment(simulator)
            return "Simulator can use 127.0.0.1."
            #else
            return "Physical devices must use the Mac LAN IP, not 127.0.0.1."
            #endif
        }
        if let lastError = snapshot.lastError, lastError.contains("Connection refused") {
            return "Check that the Python server is running on 0.0.0.0 and macOS Firewall allows Python."
        }
        return "Use the Mac LAN IP shown in Touchprint Analyzer."
    }

    private func testPromptText(for host: String) -> String {
        if host.isEmpty {
            return "Connect test is disabled until a host is entered."
        }
        return "After tapping Test Connection, iOS may ask for Local Network permission. Choose Allow."
    }

    private func shouldShowTelemetryWarning(for host: String) -> Bool {
        #if targetEnvironment(simulator)
        return host.isEmpty
        #else
        return host.isEmpty || host == "127.0.0.1" || host == "localhost" || host == "::1"
        #endif
    }

    private func telemetryWarningText(for host: String) -> String {
        #if targetEnvironment(simulator)
        if host.isEmpty {
            return "Enter Mac LAN IP, for example 192.168.1.17"
        }
        return "Simulator may use 127.0.0.1."
        #else
        if host.isEmpty {
            return "Enter Mac LAN IP, for example 192.168.1.17"
        }
        return "Use the Mac LAN IP shown in Touchprint Analyzer."
        #endif
    }
}

final class TouchCaptureSurfaceView: UIView {
    weak var captureDelegate: TouchCaptureViewDelegate?

    override init(frame: CGRect) {
        super.init(frame: frame)
        isMultipleTouchEnabled = true
        backgroundColor = .black
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        isMultipleTouchEnabled = true
        backgroundColor = .black
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesBegan(touches, with: event)
        captureDelegate?.captureView(self, didReceive: touches, phase: .began, event: event)
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesMoved(touches, with: event)
        captureDelegate?.captureView(self, didReceive: touches, phase: .moved, event: event)
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesEnded(touches, with: event)
        captureDelegate?.captureView(self, didReceive: touches, phase: .ended, event: event)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        super.touchesCancelled(touches, with: event)
        captureDelegate?.captureView(self, didReceive: touches, phase: .cancelled, event: event)
    }
}

private extension UILabel {
    static func makeCaption(_ text: String) -> UILabel {
        let label = UILabel()
        label.text = text
        label.textColor = .white
        label.font = .systemFont(ofSize: 11, weight: .semibold)
        label.setContentHuggingPriority(.required, for: .horizontal)
        return label
    }
}
