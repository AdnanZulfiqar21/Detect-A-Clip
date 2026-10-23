import Foundation

/// Lab-build legal text. Not counsel-reviewed (B-04); shown so the Terms/Privacy flow is real.
enum LegalText {
    static let termsVersion = "LAB-0.1"
    static let disclosureVersion = "SCAN-DISCLOSURE-0.1"
    static let governingLanguageVersion = "en-LAB-0.1"

    static let terms = """
    Detect A Clip — Lab Build Terms (version LAB-0.1)

    This is a research build. It recognises only self-created synthetic clips from a small \
    on-device catalogue. It does not recognise real films, series, dramas or anime, and its \
    results are not evidence of the identity of any real work.

    A scan starts only when you press Start and confirm the per-scan notice. You can stop \
    sampling or cancel unfinished matching at any time; a stopped or cancelled scan never \
    produces a result.

    Screen capture of other apps is disabled in this build. No account, purchase, \
    advertising or subscription exists. The governing language of these terms is English.
    """

    static let privacy = """
    Privacy (lab build)

    • Everything runs on this iPhone. The app makes no network requests.
    • Sampled frames are reduced to 64-bit hashes immediately and discarded. Hashes and \
    results are kept in memory only and are never written to storage.
    • A result is kept until the next scan, Discard, or 15 minutes — whichever comes first. \
    If iOS closes the app, the result is lost.
    • The only thing stored on the device is your acceptance of these terms (version, text \
    hash, locale and time), so the app does not ask again on every launch.
    • No camera, microphone, photo library, contacts, location or notification access is \
    requested.
    """
}
