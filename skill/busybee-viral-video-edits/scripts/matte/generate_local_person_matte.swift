import AVFoundation
import CoreGraphics
import CoreImage
import CoreVideo
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

enum MatteError: Error, CustomStringConvertible {
    case usage
    case noVideoTrack
    case cannotAddReaderOutput
    case cannotStartReader
    case cannotCreateImage
    case cannotWriteImage(URL)
    case readerFailed(String)

    var description: String {
        switch self {
        case .usage:
            return "usage: generate_local_person_matte <source.mp4> <proposal_dir>"
        case .noVideoTrack:
            return "source has no video track"
        case .cannotAddReaderOutput:
            return "AVAssetReader cannot add the video output"
        case .cannotStartReader:
            return "AVAssetReader could not start"
        case .cannotCreateImage:
            return "could not create a grayscale proposal image"
        case .cannotWriteImage(let url):
            return "could not write proposal image: \(url.path)"
        case .readerFailed(let message):
            return "AVAssetReader failed: \(message)"
        }
    }
}

func pixels(from pixelBuffer: CVPixelBuffer) -> [UInt8] {
    let width = CVPixelBufferGetWidth(pixelBuffer)
    let height = CVPixelBufferGetHeight(pixelBuffer)
    let rowBytes = CVPixelBufferGetBytesPerRow(pixelBuffer)
    let format = CVPixelBufferGetPixelFormatType(pixelBuffer)
    var result = [UInt8](repeating: 0, count: width * height)
    CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddress(pixelBuffer) else { return result }

    if format == kCVPixelFormatType_OneComponent8 {
        let source = base.assumingMemoryBound(to: UInt8.self)
        for y in 0..<height {
            result.replaceSubrange(
                (y * width)..<((y + 1) * width),
                with: UnsafeBufferPointer(start: source + y * rowBytes, count: width)
            )
        }
    } else if format == kCVPixelFormatType_OneComponent32Float {
        let source = base.assumingMemoryBound(to: Float.self)
        let stride = rowBytes / MemoryLayout<Float>.stride
        for y in 0..<height {
            for x in 0..<width {
                result[y * width + x] = UInt8(max(0, min(255, Int(source[y * stride + x] * 255.0))))
            }
        }
    } else {
        let image = CIImage(cvPixelBuffer: pixelBuffer).oriented(.up)
        let context = CIContext(options: [.cacheIntermediates: false])
        context.render(
            image,
            toBitmap: &result,
            rowBytes: width,
            bounds: CGRect(x: 0, y: 0, width: width, height: height),
            format: .L8,
            colorSpace: CGColorSpaceCreateDeviceGray()
        )
    }
    return result
}

func writePNG(_ pixels: [UInt8], width: Int, height: Int, url: URL) throws {
    let data = Data(pixels)
    guard
        let provider = CGDataProvider(data: data as CFData),
        let image = CGImage(
            width: width,
            height: height,
            bitsPerComponent: 8,
            bitsPerPixel: 8,
            bytesPerRow: width,
            space: CGColorSpaceCreateDeviceGray(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: false,
            intent: .defaultIntent
        )
    else {
        throw MatteError.cannotCreateImage
    }
    guard let destination = CGImageDestinationCreateWithURL(
        url as CFURL,
        UTType.png.identifier as CFString,
        1,
        nil
    ) else {
        throw MatteError.cannotWriteImage(url)
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw MatteError.cannotWriteImage(url)
    }
}

@available(macOS 14.0, *)
func generate(sourceURL: URL, proposalDirectory: URL) async throws {
    try FileManager.default.createDirectory(
        at: proposalDirectory,
        withIntermediateDirectories: true
    )
    let asset = AVURLAsset(url: sourceURL)
    guard let track = try await asset.loadTracks(withMediaType: .video).first else {
        throw MatteError.noVideoTrack
    }
    let reader = try AVAssetReader(asset: asset)
    let output = AVAssetReaderTrackOutput(
        track: track,
        outputSettings: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ]
    )
    output.alwaysCopiesSampleData = false
    guard reader.canAdd(output) else { throw MatteError.cannotAddReaderOutput }
    reader.add(output)
    guard reader.startReading() else { throw MatteError.cannotStartReader }

    var frameIndex = 0
    while let sample = output.copyNextSampleBuffer() {
        autoreleasepool {
            guard let frame = CMSampleBufferGetImageBuffer(sample) else { return }
            let width = CVPixelBufferGetWidth(frame)
            let height = CVPixelBufferGetHeight(frame)
            var proposal = [UInt8](repeating: 0, count: width * height)
            do {
                let handler = VNImageRequestHandler(
                    cvPixelBuffer: frame,
                    orientation: .up,
                    options: [:]
                )
                let request = VNGenerateForegroundInstanceMaskRequest()
                try handler.perform([request])
                if let observation = request.results?.first,
                   !observation.allInstances.isEmpty {
                    let scaled = try observation.generateScaledMaskForImage(
                        forInstances: observation.allInstances,
                        from: handler
                    )
                    proposal = pixels(from: scaled)
                }
            } catch {
                fputs("frame \(frameIndex): Vision proposal failed: \(error)\n", stderr)
            }
            let name = String(format: "proposal_%06d.png", frameIndex)
            let destination = proposalDirectory.appendingPathComponent(name)
            do {
                try writePNG(proposal, width: width, height: height, url: destination)
            } catch {
                fputs("frame \(frameIndex): \(error)\n", stderr)
            }
            frameIndex += 1
        }
    }
    if reader.status == .failed {
        throw MatteError.readerFailed(reader.error?.localizedDescription ?? "unknown error")
    }
    print("generated \(frameIndex) local foreground-instance proposals")
}

do {
    guard CommandLine.arguments.count == 3 else { throw MatteError.usage }
    guard #available(macOS 14.0, *) else {
        throw MatteError.readerFailed("macOS 14 or newer is required")
    }
    try await generate(
        sourceURL: URL(fileURLWithPath: CommandLine.arguments[1]),
        proposalDirectory: URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
    )
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
