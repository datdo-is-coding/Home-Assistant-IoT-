import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/models/device.dart';
import 'package:home_competition/widgets/channel_editor_sheet.dart';

void main() {
  Future<void> open(WidgetTester tester,
      Future<void> Function(String,DeviceType,List<String>) save,
      {List<String> aliases=const []}) async {
    await tester.pumpWidget(MaterialApp(home:Scaffold(body:Builder(builder:(context)=>TextButton(
      onPressed:()=>showModalBottomSheet<void>(context:context,isScrollControlled:true,
        builder:(_)=>ChannelEditorSheet(channelLabel:'CH1',initialName:'Đèn bể cá',
          initialType:DeviceType.light,initialAliases:aliases,onSave:save)),child:const Text('Sửa'))))));
    await tester.tap(find.text('Sửa'));await tester.pumpAndSettle();
  }
  String text(WidgetTester tester,String key)=>tester.widget<TextField>(find.byKey(Key(key))).controller!.text;

  testWidgets('alias follows name until edited independently, and can follow again',(tester) async {
    await open(tester,(a,b,c) async {});
    await tester.enterText(find.byKey(const Key('channel-name')),'Máy pha cà phê');
    expect(text(tester,'channel-aliases'),'Máy pha cà phê');
    await tester.enterText(find.byKey(const Key('channel-aliases')),'máy cà phê');
    await tester.enterText(find.byKey(const Key('channel-name')),'Máy pha mới');
    expect(text(tester,'channel-aliases'),'máy cà phê');
    await tester.enterText(find.byKey(const Key('channel-aliases')),'');
    await tester.enterText(find.byKey(const Key('channel-name')),'Máy pha espresso');
    expect(text(tester,'channel-aliases'),'Máy pha espresso');
  });

  testWidgets('saving shows progress, blocks duplicate submit, displays error and retries',(tester) async {
    final pending=Completer<void>();int calls=0;
    await open(tester,(name,type,aliases) async {
      calls++;if(calls==1)await pending.future;
      expect(aliases,['máy cà phê']);
    },aliases:['máy cà phê']);
    await tester.enterText(find.byKey(const Key('channel-name')),'Máy pha cà phê');
    expect(text(tester,'channel-aliases'),'máy cà phê');
    await tester.tap(find.text('Lưu thay đổi & Đồng bộ'));await tester.pump();
    expect(find.text('Đang lưu và đồng bộ…'),findsOneWidget);expect(calls,1);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,isNull);
    pending.completeError(Exception('Mất kết nối'));await tester.pumpAndSettle();
    expect(find.textContaining('Mất kết nối'),findsOneWidget);
    await tester.tap(find.text('Lưu thay đổi & Đồng bộ'));await tester.pumpAndSettle();
    expect(calls,2);expect(find.textContaining('Đã lưu tên'),findsOneWidget);
  });

  testWidgets('empty name is rejected before sending',(tester) async {
    int calls=0;await open(tester,(a,b,c)async{calls++;});
    await tester.enterText(find.byKey(const Key('channel-name')),'  ');
    await tester.tap(find.text('Lưu thay đổi & Đồng bộ'));await tester.pump();
    expect(calls,0);expect(find.byKey(const Key('channel-save-error')),findsOneWidget);
  });
}
