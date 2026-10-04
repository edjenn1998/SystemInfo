import sys
if '--cli' in sys.argv:
    sys.argv.remove('--cli')
    from system_info.main import main
elif '--self-test' in sys.argv:
    sys.argv.remove('--self-test')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from system_info.gui import Window
    app=QApplication(sys.argv);window=Window();window.show()
    state={'passed':False}
    def verify():
        if window.snapshot is None:
            QTimer.singleShot(100,verify);return
        state['passed']=window.tabs.count()==11
        window.close();app.quit()
    QTimer.singleShot(100,verify);QTimer.singleShot(30000,app.quit);app.exec()
    print('GUI self-test passed' if state['passed'] else 'GUI self-test failed')
    raise SystemExit(0 if state['passed'] else 1)
else:
    from system_info.gui import main
raise SystemExit(main())
