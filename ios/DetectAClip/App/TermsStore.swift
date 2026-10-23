import CryptoKit
import Foundation

/// TermsReceipt (roadmap F04). Contains no OS permission token and no scan data.
struct TermsReceipt: Codable, Equatable {
    let termsVersion: String
    let renderedTextHash: String
    let locale: String
    let governingLanguageVersion: String
    let disclosureVersion: String
    let acceptedAt: Date
}

@MainActor
final class TermsStore: ObservableObject {
    private static let defaultsKey = "termsReceipt"

    @Published private(set) var receipt: TermsReceipt?

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: Self.defaultsKey),
           let stored = try? JSONDecoder().decode(TermsReceipt.self, from: data),
           stored.termsVersion == LegalText.termsVersion,
           stored.renderedTextHash == Self.currentTextHash {
            receipt = stored
        } else {
            // Missing, unreadable or for different text: a material change needs new consent.
            defaults.removeObject(forKey: Self.defaultsKey)
        }
    }

    static var currentTextHash: String {
        let digest = SHA256.hash(data: Data((LegalText.terms + LegalText.privacy).utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    func accept() {
        let receipt = TermsReceipt(termsVersion: LegalText.termsVersion,
                                   renderedTextHash: Self.currentTextHash,
                                   locale: Locale.current.identifier,
                                   governingLanguageVersion: LegalText.governingLanguageVersion,
                                   disclosureVersion: LegalText.disclosureVersion,
                                   acceptedAt: Date())
        if let data = try? JSONEncoder().encode(receipt) {
            defaults.set(data, forKey: Self.defaultsKey)
        }
        self.receipt = receipt
    }

    func withdraw() {
        defaults.removeObject(forKey: Self.defaultsKey)
        receipt = nil
    }
}
