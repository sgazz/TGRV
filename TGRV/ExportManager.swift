import Foundation

enum ExportManager {
    static func export(session: TouchSessionExport) throws -> URL {
        let fileManager = FileManager.default
        let baseDirectory = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )

        let exportsDirectory = baseDirectory.appendingPathComponent("TouchExports", isDirectory: true)
        if !fileManager.fileExists(atPath: exportsDirectory.path) {
            try fileManager.createDirectory(
                at: exportsDirectory,
                withIntermediateDirectories: true,
                attributes: nil
            )
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        let fileName = "touch_session_\(session.sessionId.uuidString)_\(formatter.string(from: Date(timeIntervalSince1970: session.exportedAt))).json"
        let fileURL = exportsDirectory.appendingPathComponent(fileName)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .secondsSince1970

        let data = try encoder.encode(session)
        try data.write(to: fileURL, options: .atomic)
        return fileURL
    }
}
