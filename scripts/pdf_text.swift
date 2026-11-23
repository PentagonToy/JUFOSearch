import Foundation
import PDFKit

guard CommandLine.arguments.count == 2,
      let document = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])),
      let text = document.string else {
    fputs("Could not read publisher PDF\n", stderr)
    exit(1)
}
print(text)
