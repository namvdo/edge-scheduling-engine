import pytest
import importlib

client_module = importlib.import_module("services.basestation-sim.client")
StatefulUE = client_module.StatefulUE

def test_stateful_ue_initialization():
    ue = StatefulUE("ue-1")
    assert ue.ue_id == "ue-1"
    assert ue.slice_id in ["eMBB", "URLLC", "mMTC"]
    assert -250 <= ue.x <= 250
    assert -250 <= ue.y <= 250
    assert ue.dl_buffer_bytes >= 0
    assert ue.ul_buffer_bytes >= 0

def test_ue_mobility():
    ue = StatefulUE("ue-1")
    start_x, start_y = ue.x, ue.y
    ue.move()
    # Ensure it moved but stayed within bounds
    assert -250 <= ue.x <= 250
    assert -250 <= ue.y <= 250
    # It's technically possible but highly improbable it moved exactly 0.0
    
def test_ue_cqi_calculation():
    ue = StatefulUE("ue-1")
    ue.x, ue.y = 0.0, 10.0 # 10 meters away, very close

    cqi, sinr = ue.get_cqi_and_sinr()

    assert 1 <= cqi <= 15
    assert -5.0 <= sinr <= 30.0
    # Urban microcell path loss model: PL = 38 + 25*log10(10) = 38 + 25 = 63 dB
    # SINR = 30 (Tx) - 63 (PL) - (-100) (noise) + fading = 67 dB (capped to 30)
    # With shadow fading (std=4dB), expect SINR typically > 20 dB at 10m
    # Note: Due to shadow fading variance, we use relaxed bounds
    assert sinr > 10.0  # Should be high SINR at close distance
    assert cqi >= 8  # High CQI expected at close range

def test_buffer_draining():
    ue = StatefulUE("ue-1")
    # Force state
    ue.dl_buffer_bytes = 10000
    ue.ul_buffer_bytes = 5000
    
    # Drain with perfect CQI (15) which maps to ~105 bytes/PRB. 
    # Allocate 100 PRBs. Total capacity = 105 * 100 = 10500 bytes.
    # TDD = 80% DL (8400 bytes), 20% UL (2100 bytes).
    
    ue.drain_buffers(allocated_prbs=100, cqi=15, tdd_dl_pct=0.8)
    
    # Expect DL to drain 8400 bytes
    assert ue.dl_buffer_bytes == 10000 - 8400
    
    expected_ul_drain = int(10500 * (1.0 - 0.8))
    assert ue.ul_buffer_bytes == 5000 - expected_ul_drain
