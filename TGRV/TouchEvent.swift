import Foundation

enum TouchPhase: String, Codable {
    case began
    case moved
    case ended
    case cancelled
}

enum TouchSampleKind: String, Codable {
    case live
    case coalesced
    case predicted
}

enum TouchInputType: String, Codable {
    case direct
    case pencil
    case stylus
    case indirect
    case indirectPointer
    case unknown
}

enum DeviceType: String, Codable {
    case phone
    case pad
    case other
}

struct TouchEvent: Codable, Identifiable, Equatable {
    let id: UUID
    let sessionId: UUID
    let touchId: UUID
    let phase: TouchPhase
    let sampleKind: TouchSampleKind
    let sampleIndex: Int
    let sampleCount: Int
    let timestamp: Double
    let x: Double
    let y: Double
    let force: Double?
    let maximumPossibleForce: Double
    let majorRadius: Double
    let altitudeAngle: Double?
    let azimuthAngle: Double?
    let touchType: TouchInputType
    let deviceType: DeviceType
    let coalescedTouchesCount: Int
    let predictedTouchesCount: Int
}

struct TouchSessionExport: Codable, Equatable {
    let sessionId: UUID
    let startedAt: TimeInterval
    let exportedAt: TimeInterval
    let deviceType: DeviceType
    let touchEventCount: Int
    let events: [TouchEvent]
}
