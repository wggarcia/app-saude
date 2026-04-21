import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class DeviceService {
  static const _deviceKey = 'soluscrt_device_id';
  static String? _memoryDeviceId;

  static Future<String> getDeviceId() async {
    if (_memoryDeviceId != null && _memoryDeviceId!.isNotEmpty) {
      return _memoryDeviceId!;
    }

    const uuid = Uuid();
    try {
      final prefs = await SharedPreferences.getInstance();
      final current = prefs.getString(_deviceKey);
      if (current != null && current.isNotEmpty) {
        _memoryDeviceId = current;
        return current;
      }

      final created = uuid.v4();
      await prefs.setString(_deviceKey, created);
      _memoryDeviceId = created;
      return created;
    } catch (_) {
      // Em simuladores iOS o canal nativo do SharedPreferences pode falhar
      // temporariamente. O envio publico nao deve parar por causa disso.
    }

    final created = uuid.v4();
    _memoryDeviceId = created;
    return created;
  }
}
