import Foundation

final class SessionManager {
    static let shared = SessionManager()

    private struct SessionState {
        var sessionId: UUID
        var startedAt: TimeInterval
    }

    private let queue = DispatchQueue(label: "com.gazza.tgrv.session-manager", qos: .userInitiated)
    private var state: SessionState

    private init() {
        let now = Date().timeIntervalSince1970
        self.state = SessionState(sessionId: UUID(), startedAt: now)
    }

    func currentSessionId() -> UUID {
        queue.sync { state.sessionId }
    }

    func currentSessionStartedAt() -> TimeInterval {
        queue.sync { state.startedAt }
    }

    func resetSession() -> (sessionId: UUID, startedAt: TimeInterval) {
        queue.sync {
            let now = Date().timeIntervalSince1970
            let newState = SessionState(sessionId: UUID(), startedAt: now)
            state = newState
            return (newState.sessionId, newState.startedAt)
        }
    }
}
