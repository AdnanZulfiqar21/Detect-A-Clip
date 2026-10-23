import DetectAClipCore
import SwiftUI

struct LegalView: View {
    @ObservedObject var terms: TermsStore
    let manifest: PackManifest

    var body: some View {
        List {
            Section("Catalogue") {
                LabeledContent("Pack", value: manifest.packID)
                LabeledContent("Version", value: manifest.version)
                LabeledContent("Titles", value: "\(manifest.titleCount) synthetic")
                LabeledContent("Indexed", value: "\(Int(manifest.indexedSeconds)) s")
                LabeledContent("Index size", value: "\(manifest.descriptorBytes) bytes")
                LabeledContent("Calibration", value: manifest.calibrationStatus)
                LabeledContent("Rights", value: manifest.rightsBasis)
            }
            Section("Terms") {
                Text(LegalText.terms).font(.footnote)
            }
            Section("Privacy") {
                Text(LegalText.privacy).font(.footnote)
            }
            if let receipt = terms.receipt {
                Section("Your acceptance") {
                    LabeledContent("Version", value: receipt.termsVersion)
                    LabeledContent("Accepted", value: receipt.acceptedAt.formatted(date: .abbreviated, time: .shortened))
                    LabeledContent("Locale", value: receipt.locale)
                    Button("Withdraw acceptance", role: .destructive) {
                        terms.withdraw()
                    }
                }
            }
        }
        .navigationTitle("About and legal")
    }
}
