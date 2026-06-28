import Cocoa
import Foundation

// MARK: - Floating Capture Button App

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var button: NSButton!
    var statusLabel: NSTextField!
    var isRecording = false
    var process: Process?
    let outputDir: String
    
    let buttonSize: CGFloat = 64
    
    override init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        outputDir = home.appendingPathComponent("iapp/ipkgs/Pymodelverse/scrollocr").path
        super.init()
    }
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        createWindow()
        createButton()
        createStatusLabel()
    }
    
    func createWindow() {
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let x = (screenRect.width - buttonSize) / 2 + screenRect.origin.x
        let y = screenRect.origin.y + screenRect.height - buttonSize - 40
        
        let windowRect = NSRect(x: x, y: y, width: buttonSize, height: buttonSize + 20)
        
        window = NSWindow(
            contentRect: windowRect,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.level = .floating
        window.isMovableByWindowBackground = true
        window.hasShadow = false
        window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        window.makeKeyAndOrderFront(nil)
    }
    
    func createButton() {
        let contentView = window.contentView!
        
        button = NSButton(frame: NSRect(x: 0, y: 10, width: buttonSize, height: buttonSize))
        button.wantsLayer = true
        button.layer?.cornerRadius = buttonSize / 2
        button.layer?.masksToBounds = true
        button.isBordered = false
        button.bezelStyle = .shadowlessSquare
        button.action = #selector(toggleCapture)
        button.target = self
        
        setIdleStyle()
        contentView.addSubview(button)
    }
    
    func createStatusLabel() {
        let contentView = window.contentView!
        
        statusLabel = NSTextField(frame: NSRect(x: 0, y: 0, width: buttonSize, height: 12))
        statusLabel.isEditable = false
        statusLabel.isBordered = false
        statusLabel.backgroundColor = .clear
        statusLabel.textColor = NSColor(white: 0.7, alpha: 0.8)
        statusLabel.font = NSFont.systemFont(ofSize: 9)
        statusLabel.alignment = .center
        statusLabel.stringValue = "● 空闲"
        contentView.addSubview(statusLabel)
    }
    
    func setIdleStyle() {
        button.layer?.backgroundColor = NSColor(white: 0.27, alpha: 0.85).cgColor
        button.title = "●"
        button.contentTintColor = NSColor(white: 1, alpha: 0.9)
        button.font = NSFont.systemFont(ofSize: 20)
        statusLabel.stringValue = "● 空闲"
        statusLabel.textColor = NSColor(white: 0.7, alpha: 0.8)
    }
    
    func setRecordingStyle() {
        button.layer?.backgroundColor = NSColor(red: 0.8, green: 0.13, blue: 0.13, alpha: 0.85).cgColor
        button.title = "■"
        button.contentTintColor = .white
        button.font = NSFont.systemFont(ofSize: 18)
        statusLabel.stringValue = "● 录制中"
        statusLabel.textColor = NSColor(red: 1, green: 0.3, blue: 0.3, alpha: 0.9)
    }
    
    func setCompleteStyle(frameCount: Int) {
        button.layer?.backgroundColor = NSColor(red: 0.2, green: 0.67, blue: 0.2, alpha: 0.85).cgColor
        button.title = "✓"
        button.contentTintColor = .white
        button.font = NSFont.boldSystemFont(ofSize: 22)
        statusLabel.stringValue = "\(frameCount) 帧"
        statusLabel.textColor = NSColor(red: 0.3, green: 1, blue: 0.3, alpha: 0.9)
    }
    
    @objc func toggleCapture() {
        if isRecording {
            stopCapture()
        } else {
            startCapture()
        }
    }
    
    func startCapture() {
        isRecording = true
        setRecordingStyle()
        
        let pythonPath = "/Users/robin/anaconda3/envs/dsenv/bin/python3"
        let scriptDir = "/Users/robin/iapp/ipkgs/Pymodelverse"
        let scriptArgs = ["-m", "scrollocr.cli", "--auto", "--shots", "10", "--delay", "1.5"]
        
        process = Process()
        process?.executableURL = URL(fileURLWithPath: pythonPath)
        process?.arguments = scriptArgs
        process?.currentDirectoryURL = URL(fileURLWithPath: scriptDir)
        
        let outputPipe = Pipe()
        process?.standardOutput = outputPipe
        process?.standardError = outputPipe
        
        process?.terminationHandler = { [weak self] proc in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.isRecording = false
                if proc.terminationStatus == 0 {
                    self.setCompleteStyle(frameCount: 10)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                        self.setIdleStyle()
                    }
                } else {
                    self.setIdleStyle()
                    self.statusLabel.stringValue = "✗ 失败"
                }
            }
        }
        
        do {
            try process?.run()
        } catch {
            print("Failed to start Python process: \(error)")
            isRecording = false
            setIdleStyle()
        }
    }
    
    func stopCapture() {
        process?.terminate()
        process = nil
        isRecording = false
        setIdleStyle()
        statusLabel.stringValue = "● 已停止"
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            self.setIdleStyle()
        }
    }
}

// Entry point
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
