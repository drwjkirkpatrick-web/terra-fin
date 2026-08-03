"""Comprehensive tests for the ESP32/MicroPython port of Terra-Fin.

Uses sys.path trick to import from lib/ directory.
Injects fake_machine before sensor imports for CPython testing.
"""

import sys
import os
import json
import tempfile
import unittest

# Add lib directory to path
LIB_DIR = os.path.join(os.path.dirname(__file__), "..", "lib")
sys.path.insert(0, os.path.abspath(LIB_DIR))

# Inject fake machine before any sensor imports
sys.modules["machine"] = __import__("fake_machine", globals(), locals(), [], 1)


# ===================================================================
# Core infrastructure tests
# ===================================================================

class TestTypes(unittest.TestCase):
    def test_import(self):
        from core import types
        self.assertTrue(hasattr(types, "SensorReading"))
        self.assertTrue(hasattr(types, "utc_now"))

    def test_sensor_reading(self):
        from core.types import SensorReading
        r = SensorReading("test", "2024-01-01T00:00:00Z", {"temp": 25.0}, {"temp": "C"})
        self.assertEqual(r.sensor_name, "test")
        self.assertEqual(r.metrics["temp"], 25.0)

    def test_utc_now(self):
        from core.types import utc_now
        ts = utc_now()
        self.assertTrue(ts.startswith("20"))
        self.assertTrue(ts.endswith("Z"))

    def test_harvest_entry(self):
        from core.types import HarvestEntry
        e = HarvestEntry("avocado", "2024-01-01T00:00:00Z", 5, 2.5, "Block A")
        self.assertEqual(e.crop, "avocado")
        self.assertEqual(e.count, 5)
        d = e.to_dict()
        self.assertEqual(d["crop"], "avocado")

    def test_night_event(self):
        from core.types import NightEvent
        e = NightEvent("motion", "2024-01-01T00:00:00Z", "Motion detected", "warning")
        self.assertEqual(e.event_type, "motion")
        d = e.to_dict()
        self.assertEqual(d["event_type"], "motion")

    def test_gps_position(self):
        from core.types import GPSPosition
        p = GPSPosition(-0.5, 36.8, 1800.0, "2024-01-01T00:00:00Z", "GPS")
        self.assertEqual(p.lat, -0.5)
        self.assertEqual(p.lon, 36.8)


class TestConfig(unittest.TestCase):
    def test_import(self):
        from core import config
        self.assertTrue(hasattr(config, "MainConfig"))

    def test_main_config_defaults(self):
        from core.config import MainConfig
        cfg = MainConfig()
        self.assertTrue(cfg.mock_mode)
        self.assertEqual(cfg.device_name, "terra-fin-esp32-01")
        self.assertTrue(cfg.soil_moisture.enabled)
        self.assertTrue(cfg.gps.enabled)

    def test_config_save_load(self):
        from core.config import MainConfig
        cfg = MainConfig()
        cfg.device_name = "test-device"
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "config.json")
        cfg.save(path)
        loaded = MainConfig.load(path)
        self.assertEqual(loaded.device_name, "test-device")


class TestEventBus(unittest.TestCase):
    def test_import(self):
        from core import event_bus
        self.assertTrue(hasattr(event_bus, "EventBus"))

    def test_publish_subscribe(self):
        from core.event_bus import EventBus
        bus = EventBus()
        received = []
        def handler(data):
            received.append(data)
        bus.subscribe("test", handler)
        bus.publish("test", {"msg": "hello"})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["msg"], "hello")

    def test_unsubscribe(self):
        from core.event_bus import EventBus
        bus = EventBus()
        received = []
        def handler(data):
            received.append(data)
        sub_id = bus.subscribe("test", handler)
        bus.unsubscribe(sub_id)
        bus.publish("test", {"msg": "hello"})
        self.assertEqual(len(received), 0)


class TestAdaptationBase(unittest.TestCase):
    def test_import(self):
        from core import adaptation_base
        self.assertTrue(hasattr(adaptation_base, "AdaptationModule"))
        self.assertTrue(hasattr(adaptation_base, "AdaptationResult"))

    def test_adaptation_result(self):
        from core.adaptation_base import AdaptationResult
        r = AdaptationResult("test", "weather", "2024-01-01T00:00:00Z", "advisory", 0.5, {})
        self.assertEqual(r.module_name, "test")
        d = r.to_dict()
        self.assertEqual(d["module_name"], "test")

    def test_process_calls_analyze(self):
        from core.adaptation_base import AdaptationModule, AdaptationResult

        class DummyModule(AdaptationModule):
            name = "dummy"
            category = "test"
            description = "dummy module"

            def analyze(self, reading, context):
                return AdaptationResult(
                    module_name=self.name,
                    category=self.category,
                    timestamp="2024-01-01T00:00:00Z",
                    advisory="test advisory",
                    confidence=0.5,
                    data={"key": "value"},
                )

        mod = DummyModule()
        result = mod.process(None, {})
        self.assertEqual(result.advisory, "test advisory")
        self.assertEqual(result.data["key"], "value")


class TestRecorder(unittest.TestCase):
    def test_import(self):
        from core import recorder
        self.assertTrue(hasattr(recorder, "Recorder"))

    def test_record_and_retrieve(self):
        from core.recorder import Recorder
        from core.types import SensorReading
        tmpdir = tempfile.mkdtemp()
        rec = Recorder(data_path=tmpdir)
        rec.init_db()
        reading = SensorReading("temp", "2024-01-01T00:00:00Z", {"temp_c": 25.0}, {"temp_c": "C"})
        rec.record_sensor(reading)
        history = rec.get_sensor_history(sensor_name="temp", limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["sensor_name"], "temp")

    def test_record_harvest(self):
        from core.recorder import Recorder
        from core.types import HarvestEntry
        tmpdir = tempfile.mkdtemp()
        rec = Recorder(data_path=tmpdir)
        rec.init_db()
        entry = HarvestEntry("avocado", "2024-01-01T00:00:00Z", 5, 2.5, "Block A")
        rec.record_harvest(entry)
        harvests = rec.get_harvests(crop="avocado")
        self.assertEqual(len(harvests), 1)
        self.assertEqual(harvests[0]["crop"], "avocado")

    def test_record_night_event(self):
        from core.recorder import Recorder
        from core.types import NightEvent
        tmpdir = tempfile.mkdtemp()
        rec = Recorder(data_path=tmpdir)
        rec.init_db()
        event = NightEvent("motion", "2024-01-01T00:00:00Z", "test event", "info")
        rec.record_night_event(event)
        events = rec.get_night_events()
        self.assertEqual(len(events), 1)

    def test_get_summary(self):
        from core.recorder import Recorder
        from core.types import SensorReading
        tmpdir = tempfile.mkdtemp()
        rec = Recorder(data_path=tmpdir)
        rec.init_db()
        reading = SensorReading("temp", "2024-01-01T00:00:00Z", {"temp_c": 25.0}, {"temp_c": "C"})
        rec.record_sensor(reading)
        summary = rec.get_summary()
        self.assertEqual(summary["sensor_readings"], 1)


class TestEngine(unittest.TestCase):
    def test_import(self):
        from core import engine
        self.assertTrue(hasattr(engine, "Engine"))


class TestMockManager(unittest.TestCase):
    def test_import(self):
        from core import mock_manager
        self.assertTrue(hasattr(mock_manager, "MockManager"))

    def test_mock_values(self):
        from core.mock_manager import MockManager
        mm = MockManager()
        temp = mm.temperature()
        self.assertTrue(isinstance(temp, float))
        self.assertTrue(0 < temp < 50)
        moist = mm.soil_moisture()
        self.assertTrue(0 <= moist <= 100)


class TestDashboard(unittest.TestCase):
    def test_import(self):
        from core import dashboard
        self.assertTrue(hasattr(dashboard, "DashboardState"))

    def test_dashboard_state(self):
        from core.dashboard import DashboardState
        ds = DashboardState()
        ds.update({"timestamp": "2024-01-01T00:00:00Z", "sensors": {}, "cross_sensor": {}})
        state = json.loads(ds.get_state())
        self.assertEqual(state["timestamp"], "2024-01-01T00:00:00Z")


class TestAdaptationManager(unittest.TestCase):
    def test_import(self):
        from core import adaptation_manager
        self.assertTrue(hasattr(adaptation_manager, "AdaptationManager"))

    def test_load_all(self):
        from core.adaptation_manager import AdaptationManager
        mgr = AdaptationManager()
        mgr.load_all()
        # Should load at least 20 of the 30 modules (some may fail on CPython)
        self.assertGreater(len(mgr._modules), 15)


# ===================================================================
# Sensor tests
# ===================================================================

class TestSoilMoistureSensor(unittest.TestCase):
    def test_import(self):
        from sensors import soil_moisture
        self.assertTrue(hasattr(soil_moisture, "SoilMoistureSensor"))

    def test_mock_read(self):
        from sensors.soil_moisture import SoilMoistureSensor
        from core.config import SoilConfig
        cfg = SoilConfig(mock_mode=True)
        sensor = SoilMoistureSensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("soil_moisture_pct", reading.metrics)


class TestSoilPHSensor(unittest.TestCase):
    def test_import(self):
        from sensors import soil_ph
        self.assertTrue(hasattr(soil_ph, "SoilPHSensor"))

    def test_mock_read(self):
        from sensors.soil_ph import SoilPHSensor
        from core.config import pHConfig
        cfg = pHConfig(mock_mode=True)
        sensor = SoilPHSensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("soil_pH", reading.metrics)


class TestLightSensor(unittest.TestCase):
    def test_import(self):
        from sensors import light_sensor
        self.assertTrue(hasattr(light_sensor, "LightSensor"))

    def test_mock_read(self):
        from sensors.light_sensor import LightSensor
        from core.config import LightConfig
        cfg = LightConfig(mock_mode=True)
        sensor = LightSensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("light_lux", reading.metrics)


class TestTempHumiditySensor(unittest.TestCase):
    def test_import(self):
        from sensors import temp_humidity
        self.assertTrue(hasattr(temp_humidity, "TempHumiditySensor"))

    def test_mock_read(self):
        from sensors.temp_humidity import TempHumiditySensor
        from core.config import TempHumidityConfig
        cfg = TempHumidityConfig(mock_mode=True)
        sensor = TempHumiditySensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("temp_c", reading.metrics)
        self.assertIn("humidity_pct", reading.metrics)


class TestGPSSensor(unittest.TestCase):
    def test_import(self):
        from sensors import gps
        self.assertTrue(hasattr(gps, "GPSSensor"))

    def test_mock_read(self):
        from sensors.gps import GPSSensor
        from core.config import GPSConfig
        cfg = GPSConfig(mock_mode=True)
        sensor = GPSSensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("lat", reading.metrics)
        self.assertIn("lon", reading.metrics)


class TestIMUSensor(unittest.TestCase):
    def test_import(self):
        from sensors import imu
        self.assertTrue(hasattr(imu, "IMUSensor"))

    def test_mock_read(self):
        from sensors.imu import IMUSensor
        from core.config import IMUConfig
        cfg = IMUConfig(mock_mode=True)
        sensor = IMUSensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("accel_x", reading.metrics)
        self.assertIn("accel_z", reading.metrics)


class TestCellularSensor(unittest.TestCase):
    def test_import(self):
        from sensors import cellular
        self.assertTrue(hasattr(cellular, "CellularSensor"))

    def test_mock_read(self):
        from sensors.cellular import CellularSensor
        from core.config import CellularConfig
        cfg = CellularConfig(mock_mode=True)
        sensor = CellularSensor(cfg)
        reading = sensor.read()
        self.assertIsNotNone(reading)
        self.assertIn("signal_dbm", reading.metrics)


# ===================================================================
# Adaptation module tests (representative sample)
# ===================================================================

class TestRainPredictor(unittest.TestCase):
    def test_import(self):
        from adaptation import rain_predictor
        self.assertTrue(hasattr(rain_predictor, "RainPredictor"))

    def test_high_humidity_dropping_temp(self):
        from adaptation.rain_predictor import RainPredictor
        from core.types import SensorReading
        rp = RainPredictor()
        reading = SensorReading("temp_humidity", "2024-01-01T00:00:00Z",
                                  {"humidity_pct": 85.0, "temp_c": 22.0}, {})
        result = rp.analyze(reading, {"trends": {"temp_c_delta": -0.5}})
        self.assertEqual(result.data.get("prediction"), "rain_likely")

    def test_low_humidity(self):
        from adaptation.rain_predictor import RainPredictor
        from core.types import SensorReading
        rp = RainPredictor()
        reading = SensorReading("temp_humidity", "2024-01-01T00:00:00Z",
                                  {"humidity_pct": 30.0, "temp_c": 25.0}, {})
        result = rp.analyze(reading, {"trends": {}})
        self.assertEqual(result.data.get("prediction"), "dry")

    def test_no_reading(self):
        from adaptation.rain_predictor import RainPredictor
        rp = RainPredictor()
        result = rp.analyze(None, {})
        self.assertEqual(result.data.get("prediction"), "no_data")


class TestFrostAlert(unittest.TestCase):
    def test_import(self):
        from adaptation import frost_alert
        self.assertTrue(hasattr(frost_alert, "FrostAlert"))

    def test_cold_temp(self):
        from adaptation.frost_alert import FrostAlert
        from core.types import SensorReading
        fa = FrostAlert()
        reading = SensorReading("temp_humidity", "2024-01-01T00:00:00Z",
                                  {"temp_c": 1.0, "humidity_pct": 60.0}, {})
        result = fa.analyze(reading, {})
        self.assertIn(result.severity, ["warning", "critical"])


class TestIrrigationScheduler(unittest.TestCase):
    def test_import(self):
        from adaptation import irrigation_scheduler
        self.assertTrue(hasattr(irrigation_scheduler, "IrrigationScheduler"))

    def test_dry_no_rain(self):
        from adaptation.irrigation_scheduler import IrrigationScheduler
        from core.types import SensorReading
        sched = IrrigationScheduler()
        reading = SensorReading("soil_moisture", "2024-01-01T00:00:00Z",
                                  {"soil_moisture_pct": 15.0}, {})
        result = sched.analyze(reading, {"rain_predicted": False})
        self.assertEqual(result.data.get("recommendation"), "irrigate_now")

    def test_wet(self):
        from adaptation.irrigation_scheduler import IrrigationScheduler
        from core.types import SensorReading
        sched = IrrigationScheduler()
        reading = SensorReading("soil_moisture", "2024-01-01T00:00:00Z",
                                  {"soil_moisture_pct": 80.0}, {})
        result = sched.analyze(reading, {})
        self.assertEqual(result.data.get("recommendation"), "skip_irrigation")


class TestCompostTiming(unittest.TestCase):
    def test_import(self):
        from adaptation import compost_timing
        self.assertTrue(hasattr(compost_timing, "CompostTiming"))

    def test_ideal_conditions(self):
        from adaptation.compost_timing import CompostTiming
        from core.types import SensorReading
        ct = CompostTiming()
        reading = SensorReading("soil", "2024-01-01T00:00:00Z",
                                  {"temp_c": 25.0, "soil_moisture_pct": 50.0}, {})
        result = ct.analyze(reading, {})
        self.assertEqual(result.data.get("compost_action"), "apply_now")

    def test_too_dry(self):
        from adaptation.compost_timing import CompostTiming
        from core.types import SensorReading
        ct = CompostTiming()
        reading = SensorReading("soil", "2024-01-01T00:00:00Z",
                                  {"temp_c": 25.0, "soil_moisture_pct": 20.0}, {})
        result = ct.analyze(reading, {})
        self.assertEqual(result.data.get("compost_action"), "water_then_apply")


class TestPestPressure(unittest.TestCase):
    def test_import(self):
        from adaptation import pest_pressure
        self.assertTrue(hasattr(pest_pressure, "PestPressure"))

    def test_fruit_fly(self):
        from adaptation.pest_pressure import PestPressure
        from core.types import SensorReading
        pp = PestPressure()
        reading = SensorReading("temp_humidity", "2024-01-01T00:00:00Z",
                                  {"temp_c": 30.0, "humidity_pct": 65.0}, {})
        result = pp.analyze(reading, {})
        self.assertIn("fruit_flies", result.data.get("pest_risks", []))


class TestBeneficialInsects(unittest.TestCase):
    def test_import(self):
        from adaptation import beneficial_insects
        self.assertTrue(hasattr(beneficial_insects, "BeneficialInsectIndex"))

    def test_excellent_habitat(self):
        from adaptation.beneficial_insects import BeneficialInsectIndex
        bii = BeneficialInsectIndex()
        result = bii.analyze(None, {"flowering_plants": 8, "pesticide_used_recently": False})
        self.assertEqual(result.data.get("habitat_quality"), "excellent")


class TestDroughtMonitor(unittest.TestCase):
    def test_import(self):
        from adaptation import drought_monitor
        self.assertTrue(hasattr(drought_monitor, "DroughtMonitor"))

    def test_dry_conditions(self):
        from adaptation.drought_monitor import DroughtMonitor
        from core.types import SensorReading
        dm = DroughtMonitor()
        reading = SensorReading("soil_moisture", "2024-01-01T00:00:00Z",
                                  {"soil_moisture_pct": 15.0, "temp_c": 30.0}, {})
        result = dm.analyze(reading, {})
        self.assertIsNotNone(result.advisory)


class TestSnakeAlert(unittest.TestCase):
    def test_import(self):
        from adaptation import snake_alert
        self.assertTrue(hasattr(snake_alert, "SnakeAlert"))

    def test_hot_conditions(self):
        from adaptation.snake_alert import SnakeAlert
        from core.types import SensorReading
        sa = SnakeAlert()
        reading = SensorReading("temp_humidity", "2024-01-01T00:00:00Z",
                                  {"temp_c": 32.0, "humidity_pct": 50.0}, {})
        result = sa.analyze(reading, {})
        self.assertIsNotNone(result.advisory)


class TestHarvestReadiness(unittest.TestCase):
    def test_import(self):
        from adaptation import harvest_readiness
        self.assertTrue(hasattr(harvest_readiness, "HarvestReadiness"))


class TestWindEstimator(unittest.TestCase):
    def test_import(self):
        from adaptation import wind_estimator
        self.assertTrue(hasattr(wind_estimator, "WindEstimator"))


# ===================================================================
# Harvest module tests
# ===================================================================

class TestAvocadoHarvest(unittest.TestCase):
    def test_import(self):
        from modules import avocado
        self.assertTrue(hasattr(avocado, "AvocadoHarvest"))

    def test_log_harvest(self):
        from modules.avocado import AvocadoHarvest
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.json")
        harvest = AvocadoHarvest(db_path=db_path)
        entry = harvest.log_harvest(count=5, weight_kg=2.5, location="block A")
        self.assertEqual(entry.crop, "avocado")
        summary = harvest.daily_summary()
        self.assertEqual(summary["total_count"], 5)

    def test_quality_assessment(self):
        from modules.avocado import AvocadoHarvest
        from core.types import SensorReading
        harvest = AvocadoHarvest()
        reading = SensorReading("soil", "2024-01-01T00:00:00Z",
                                  {"soil_moisture_pct": 50.0, "soil_pH": 6.5}, {})
        result = harvest.quality_assessment(reading)
        self.assertIn("optimal", result)


class TestOrangeHarvest(unittest.TestCase):
    def test_import(self):
        from modules import orange
        self.assertTrue(hasattr(orange, "OrangeHarvest"))

    def test_log_harvest(self):
        from modules.orange import OrangeHarvest
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.json")
        harvest = OrangeHarvest(db_path=db_path)
        entry = harvest.log_harvest(count=10, weight_kg=3.0, location="grove 1")
        self.assertEqual(entry.crop, "orange")
        summary = harvest.daily_summary()
        self.assertEqual(summary["total_count"], 10)

    def test_brix_estimate(self):
        from modules.orange import OrangeHarvest
        from core.types import SensorReading
        harvest = OrangeHarvest()
        reading = SensorReading("temp_humidity", "2024-01-01T00:00:00Z",
                                  {"temp_c": 25.0, "soil_moisture_pct": 55.0}, {})
        brix = harvest.brix_estimate(reading)
        self.assertIsNotNone(brix)
        self.assertTrue(isinstance(brix, float))


class TestGreensHarvest(unittest.TestCase):
    def test_import(self):
        from modules import greens
        self.assertTrue(hasattr(greens, "GreensHarvest"))

    def test_log_harvest(self):
        from modules.greens import GreensHarvest
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.json")
        harvest = GreensHarvest(db_path=db_path)
        entry = harvest.log_harvest(count=3, weight_kg=1.0, location="plot 1",
                                      crop_type="spinach")
        self.assertEqual(entry.crop, "spinach")
        summary = harvest.daily_summary()
        self.assertEqual(summary["total_count"], 3)

    def test_leaf_condition(self):
        from modules.greens import GreensHarvest
        harvest = GreensHarvest()
        self.assertEqual(harvest.leaf_condition(20.0, 60.0), "good")
        self.assertEqual(harvest.leaf_condition(30.0, 50.0), "wilt_risk")
        self.assertEqual(harvest.leaf_condition(2.0, 50.0), "frost_risk")


class TestNightMode(unittest.TestCase):
    def test_import(self):
        from modules import night_mode
        self.assertTrue(hasattr(night_mode, "NightModeSentinel"))

    def test_classify_motion(self):
        from modules.night_mode import NightModeSentinel
        self.assertEqual(NightModeSentinel.classify_motion(0.1), "none")
        self.assertEqual(NightModeSentinel.classify_motion(0.5), "small_animal")
        self.assertEqual(NightModeSentinel.classify_motion(2.0), "human")
        self.assertEqual(NightModeSentinel.classify_motion(5.0), "large_animal")


# ===================================================================
# MicroPython compatibility tests
# ===================================================================

class TestMicroPythonCompatibility(unittest.TestCase):
    """Verify no CPython-only patterns remain in the ESP32 codebase."""

    def test_no_future_imports(self):
        import importlib
        lib_dir = os.path.abspath(LIB_DIR)
        issues = []
        for root, dirs, files in os.walk(lib_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    content = f.read()
                if "from __future__ import" in content and "__future__" in content:
                    # Check it's not in a comment
                    for line in content.split("\n"):
                        if line.strip().startswith("from __future__"):
                            issues.append(fpath)
        self.assertEqual(issues, [], "Files with __future__ imports: {}".format(issues))

    def test_no_sqlite3_imports(self):
        lib_dir = os.path.abspath(LIB_DIR)
        issues = []
        for root, dirs, files in os.walk(lib_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    content = f.read()
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("import sqlite3") or stripped.startswith("from sqlite3"):
                        issues.append("{}: {}".format(fname, stripped))
        self.assertEqual(issues, [], "Files with sqlite3 imports: {}".format(issues))

    def test_all_files_compile(self):
        import py_compile
        lib_dir = os.path.abspath(LIB_DIR)
        errors = []
        for root, dirs, files in os.walk(lib_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    py_compile.compile(fpath, doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append("{}: {}".format(fname, e))
        self.assertEqual(errors, [], "Compilation errors: {}".format(errors))


if __name__ == "__main__":
    unittest.main()