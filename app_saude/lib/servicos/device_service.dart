import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class DeviceService {
  static const _deviceKey = 'soluscrt_device_id';

  static Future<String> getDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    final current = prefs.getString(_deviceKey);
    if (current != null && current.isNotEmpty) {
      return current;
    }

    const uuid = Uuid();
    final created = uuid.v4();
    await prefs.setString(_deviceKey, created);
    return created;
  }
}
