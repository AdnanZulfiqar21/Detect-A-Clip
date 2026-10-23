import SwiftUI
import UIKit

struct RootView: View {
    @StateObject private var terms = TermsStore()
    @StateObject private var scans = ScanController()
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            if terms.receipt == nil {
                OnboardingView(terms: terms)
            } else {
                HomeView(scans: scans, terms: terms)
            }
        }
        .onChange(of: scenePhase) { newPhase in
            scans.scenePhaseChanged(newPhase)
        }
        .onReceive(NotificationCenter.default.publisher(
            for: UIApplication.protectedDataWillBecomeUnavailableNotification)) { _ in
            scans.deviceWillLock()
        }
    }
}
