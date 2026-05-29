import UIKit

protocol TouchCaptureViewDelegate: AnyObject {
    func captureView(_ view: TouchCaptureView, didReceive touches: Set<UITouch>, phase: TouchPhase, event: UIEvent?)
}

final class TouchCaptureViewController: UIViewController, TouchCaptureViewDelegate {
    private let statusLabel = UILabel()

    override func loadView() {
        let captureView = TouchCaptureView()
        captureView.captureDelegate = self
        view = captureView
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        overrideUserInterfaceStyle = .dark
        view.backgroundColor = .black
        view.isMultipleTouchEnabled = true

        navigationItem.title = "Touchprint Logger"
        navigationItem.rightBarButtonItem = UIBarButtonItem(
            title: "Export",
            style: .plain,
            target: self,
            action: #selector(exportSession)
        )

        let doubleTapRecognizer = UITapGestureRecognizer(target: self, action: #selector(handleDoubleTap))
        doubleTapRecognizer.numberOfTapsRequired = 2
        doubleTapRecognizer.cancelsTouchesInView = false
        view.addGestureRecognizer(doubleTapRecognizer)

        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        statusLabel.textColor = .white
        statusLabel.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        statusLabel.numberOfLines = 0
        statusLabel.text = "Session \(SessionManager.shared.currentSessionId().uuidString)\nEvents \(TouchLogger.shared.eventCount())"
        view.addSubview(statusLabel)

        NSLayoutConstraint.activate([
            statusLabel.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 12),
            statusLabel.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12)
        ])
    }

    func captureView(_ view: TouchCaptureView, didReceive touches: Set<UITouch>, phase: TouchPhase, event: UIEvent?) {
        let totalEvents = TouchLogger.shared.recordTouches(touches, phase: phase, in: view, event: event)
        statusLabel.text = "Session \(SessionManager.shared.currentSessionId().uuidString)\nEvents \(totalEvents)"
    }

    @objc private func handleDoubleTap() {
        TouchLogger.shared.resetSession()
        statusLabel.text = "Session \(SessionManager.shared.currentSessionId().uuidString)\nEvents 0"
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
}

final class TouchCaptureView: UIView {
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
