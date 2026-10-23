import SwiftUI

/// First use: explain the limited scope, show Terms/Privacy, require explicit acceptance.
/// Declining leaves scanning disabled while the legal text stays readable. No permission of
/// any kind is requested at app open.
struct OnboardingView: View {
    @ObservedObject var terms: TermsStore
    @State private var declined = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    SyntheticBanner()
                    Text("Detect A Clip recognises a clip only when you ask it to, and only against a small catalogue stored on this iPhone.")
                        .font(.body)
                    Text("This lab build knows synthetic test clips only. Screen capture of other apps is not enabled yet.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    GroupBox("Terms") {
                        Text(LegalText.terms).font(.footnote).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox("Privacy") {
                        Text(LegalText.privacy).font(.footnote).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    if declined {
                        Text("Scanning stays off until you accept. You can come back to these terms at any time.")
                            .font(.callout)
                            .foregroundStyle(.orange)
                    }
                    Button {
                        terms.accept()
                    } label: {
                        Text("Accept and continue").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Decline", role: .cancel) {
                        declined = true
                    }
                    .frame(maxWidth: .infinity)
                }
                .padding()
            }
            .navigationTitle("Welcome")
        }
    }
}

struct SyntheticBanner: View {
    var body: some View {
        Label("LAB BUILD · SYNTHETIC CATALOGUE ONLY", systemImage: "flask")
            .font(.caption.weight(.bold))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.orange.opacity(0.2), in: Capsule())
            .foregroundStyle(.orange)
            .accessibilityLabel("Lab build. Synthetic catalogue only.")
    }
}
