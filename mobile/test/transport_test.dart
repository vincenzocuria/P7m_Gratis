import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:p7m_gratis/core/revocation.dart';

void main() {
  test('Pinned HTTPS sends TLS and never a plaintext OCSP request', () async {
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final firstBytes = server.first.then((socket) async {
      final bytes = await socket.first;
      socket.destroy();
      return bytes;
    });
    final task = await connectPinned(
      Uri.parse('https://localhost:${server.port}'),
      InternetAddress.loopbackIPv4,
    );
    await expectLater(task.socket, throwsA(isA<HandshakeException>()));
    final bytes = await firstBytes;
    expect(bytes.first, 0x16, reason: 'TLS handshake record');
    expect(bytes[1], 0x03, reason: 'TLS protocol version');
    await server.close();
  });

  test('Pinned HTTP remains available for signed CRL transport', () async {
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final accepted = server.first;
    final task = await connectPinned(
      Uri.parse('http://localhost:${server.port}'),
      InternetAddress.loopbackIPv4,
    );
    final socket = await task.socket;
    final peer = await accepted;
    socket.destroy();
    peer.destroy();
    await server.close();
  });
}
