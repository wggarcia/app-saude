import UIKit
import Flutter
import GoogleMaps

@main
@objc class AppDelegate: FlutterAppDelegate {

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {

    GMSServices.provideAPIKey("AIzaSyDdgJLI8PGI4IO2yIRTwZOnwQKu23O6hZU")

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}