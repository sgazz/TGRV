import Foundation
import CoreGraphics

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

struct TouchPinMetadata: Codable, Equatable, Sendable {
    let experimentMode: String
    let pinSequenceId: UUID
    let pinSequence: String?
    let digit: String?
    let digitIndex: Int?
    let keypadButtonId: String
    let keypadAction: String?
    let expectedPin: String?
    let enteredPinSoFar: String?
    let isPinSubmit: Bool?
    let isPinClear: Bool?
    let buttonFrameX: Double?
    let buttonFrameY: Double?
    let buttonFrameWidth: Double?
    let buttonFrameHeight: Double?

    init(
        experimentMode: String = "pin_entry",
        pinSequenceId: UUID,
        pinSequence: String? = nil,
        digit: String? = nil,
        digitIndex: Int? = nil,
        keypadButtonId: String,
        keypadAction: String? = nil,
        expectedPin: String? = nil,
        enteredPinSoFar: String? = nil,
        isPinSubmit: Bool? = nil,
        isPinClear: Bool? = nil,
        buttonFrame: CGRect? = nil
    ) {
        self.experimentMode = experimentMode
        self.pinSequenceId = pinSequenceId
        self.pinSequence = pinSequence
        self.digit = digit
        self.digitIndex = digitIndex
        self.keypadButtonId = keypadButtonId
        self.keypadAction = keypadAction
        self.expectedPin = expectedPin
        self.enteredPinSoFar = enteredPinSoFar
        self.isPinSubmit = isPinSubmit
        self.isPinClear = isPinClear
        if let buttonFrame {
            self.buttonFrameX = Double(buttonFrame.origin.x)
            self.buttonFrameY = Double(buttonFrame.origin.y)
            self.buttonFrameWidth = Double(buttonFrame.size.width)
            self.buttonFrameHeight = Double(buttonFrame.size.height)
        } else {
            self.buttonFrameX = nil
            self.buttonFrameY = nil
            self.buttonFrameWidth = nil
            self.buttonFrameHeight = nil
        }
    }
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
    let inputType: String
    let coalescedTouchesCount: Int
    let predictedTouchesCount: Int
    let experimentMode: String?
    let pinSequenceId: UUID?
    let pinSequence: String?
    let digit: String?
    let digitIndex: Int?
    let keypadButtonId: String?
    let keypadAction: String?
    let expectedPin: String?
    let enteredPinSoFar: String?
    let isPinSubmit: Bool?
    let isPinClear: Bool?
    let buttonFrameX: Double?
    let buttonFrameY: Double?
    let buttonFrameWidth: Double?
    let buttonFrameHeight: Double?
}

struct TouchSessionExport: Codable, Equatable {
    let sessionId: UUID
    let startedAt: TimeInterval
    let exportedAt: TimeInterval
    let deviceType: DeviceType
    let inputType: String
    let touchEventCount: Int
    let events: [TouchEvent]
}
