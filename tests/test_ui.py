import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import app

class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt=QApplication.instance() or QApplication([])
        cls.qt.setStyle("Fusion")
        cls.qt.setStyleSheet(app.STYLE)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.report_patch=patch.object(app.engine,"REPORTS",Path(self.temp.name)/"reports")
        self.report_patch.start()
        self.window=app.Window()
        self.window.show()
        self.qt.processEvents()

    def tearDown(self):
        self.window.close()
        self.qt.processEvents()
        self.window.deleteLater()
        self.report_patch.stop()
        self.temp.cleanup()

    def test_navigation_and_empty_history(self):
        for index in (1,2,3,0):
            self.window.navigate(index)
            self.assertEqual(self.window.pages.currentIndex(),index)
        self.assertFalse(self.window.export.isEnabled())

    def test_bad_input_remains_actionable(self):
        self.window.target.setText("--help")
        self.window.start_scan()
        self.assertIsNone(self.window.worker)
        self.assertIn("Usernames",self.window.hint.text())
        self.assertTrue(self.window.start.isEnabled())

    def test_real_photo_scan_history_and_filter(self):
        path=Path(self.temp.name)/"test photo.png"
        Image.new("RGB",(80,60),"#78c7e3").save(path)
        self.window.target.setText(str(path))
        self.window.start_scan()
        self.assertFalse(self.window.start.isEnabled())
        deadline=time.monotonic()+15
        while self.window.worker and time.monotonic()<deadline:
            self.qt.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.worker)
        self.assertEqual(self.window.report["status"],"complete")
        self.assertEqual(self.window.table.rowCount(),5)
        self.assertTrue(self.window.export.isEnabled())
        self.window.filter.setText("SHA-256")
        visible=[i for i in range(self.window.table.rowCount()) if not self.window.table.isRowHidden(i)]
        self.assertEqual(len(visible),1)
        self.window.navigate(1)
        self.assertEqual(len(self.window.history_data),1)
        self.window.history_list.setCurrentRow(0)
        self.window.load_selected_history()
        self.assertEqual(self.window.pages.currentIndex(),0)
        self.assertEqual(self.window.filter.text(),"")

    def test_sorted_table_keeps_url_with_correct_row(self):
        rows=[{"category":"Account","label":n,"value":f"https://example.org/{n}","source":"Test","url":f"https://example.org/{n}"} for n in ("Z","A")]
        self.window.populate(rows)
        self.window.table.sortItems(1,Qt.SortOrder.AscendingOrder)
        self.assertEqual(self.window.table.item(0,1).text(),"A")
        self.assertEqual(self.window.table.item(0,2).data(Qt.ItemDataRole.UserRole),"https://example.org/A")

    def test_link_chart_follows_scan_events(self):
        chart=self.window.chart
        chart.begin("example.org","domain")
        self.window.on_event({"state":"plan","total":2,"tools":["DNS","theHarvester"]})
        self.window.on_event({"state":"running","tool":"DNS"})
        self.assertEqual([n["status"] for n in chart.nodes],["running","pending"])
        result={"tool":"DNS","status":"ok","ok":True,"log":"","records":[{"type":"A","value":"192.0.2.1"},{"type":"MX","value":"0 ."}]}
        self.window.on_event({"state":"done","tool":"DNS","result":result})
        self.assertEqual(chart.nodes[0]["count"],2)
        self.assertEqual(len(chart.nodes[0]["pins"]),2)
        self.assertEqual(self.window.count.value,2)
        self.window.chart.grab()

    def test_rows_keep_source_order_until_sorted(self):
        rows=[{"category":c,"label":c,"value":c,"source":"Test","url":""} for c in ("DNS","Host","IP address")]
        self.window.populate(rows)
        self.assertEqual([self.window.table.item(i,0).text() for i in range(3)],["DNS","HOST","IP ADDRESS"])

if __name__=="__main__":
    unittest.main()
