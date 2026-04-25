import UIKit
import Flutter
import GoogleMaps

@main
@objc class AppDelegate: FlutterAppDelegate {

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    if let apiKey = Bundle.main.object(forInfoDictionaryKey: "GMSApiKey") as? String,
       !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      GMSServices.provideAPIKey(apiKey)
    }

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
