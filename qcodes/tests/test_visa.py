import re
from pathlib import Path

import pytest
import pyvisa
import pyvisa.constants

from qcodes.instrument.visa import VisaInstrument
from qcodes.validators import Numbers


class MockVisa(VisaInstrument):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_parameter('state',
                           get_cmd='STAT?', get_parser=float,
                           set_cmd='STAT:{:.3f}',
                           vals=Numbers(-20, 20))

    def _open_resource(self, address: str, visalib):
        return MockVisaHandle(), visalib


class MockVisaHandle(pyvisa.resources.MessageBasedResource):
    """
    mock the API needed for a visa handle that throws lots of errors:

    - any write command sets a single "state" variable to a float
      after the last : in the command
    - a negative number results in an error raised here
    - 0 results in a return code for visa timeout
    - any ask command returns the state
    - a state > 10 throws an error
    """
    def __init__(self):
        self.state = 0
        self.closed = False

    def clear(self):
        self.state = 0

    def close(self):
        # make it an error to ask or write after close
        self.closed = True

    def write(self, cmd):
        if self.closed:
            raise RuntimeError("Trying to write to a closed instrument")
        num = float(cmd.split(':')[-1])
        self.state = num

        if num < 0:
            raise ValueError('be more positive!')

        if num == 0:
            raise pyvisa.VisaIOError(pyvisa.constants.VI_ERROR_TMO)

        return len(cmd)

    def ask(self, cmd):
        if self.closed:
            raise RuntimeError("Trying to ask a closed instrument")
        if self.state > 10:
            raise ValueError("I'm out of fingers")
        return self.state

    def query(self, cmd):
        if self.state > 10:
            raise ValueError("I'm out of fingers")
        return self.state

    def set_visa_attribute(
            self, name, state
    ):
        setattr(self, str(name), state)

    def __del__(self):
        pass


 # error args for set(-10)
args1 = [
    'be more positive!',
    "writing 'STAT:-10.000' to <MockVisa: Joe>",
    'setting Joe_state to -10'
]

# error args for set(0)
args2 = [
    "writing 'STAT:0.000' to <MockVisa: Joe>",
    'setting Joe_state to 0'
]

# error args for get -> 15
args3 = [
    "I'm out of fingers",
    "asking 'STAT?' to <MockVisa: Joe>",
    'getting Joe_state'
]


@pytest.fixture(name='mock_visa')
def _make_mock_visa():
    mv = MockVisa('Joe', 'none_address')
    try:
        yield mv
    finally:
        mv.close()


def test_ask_write_local(mock_visa):

    # test normal ask and write behavior
    mock_visa.state.set(2)
    assert mock_visa.state.get() == 2
    mock_visa.state.set(3.4567)
    assert mock_visa.state.get() == 3.457  # driver rounds to 3 digits

    # test ask and write errors
    with pytest.raises(ValueError) as e:
        mock_visa.state.set(-10)
    for arg in args1:
        assert arg in str(e.value)
    assert mock_visa.state.get() == -10  # set still happened

    with pytest.raises(pyvisa.VisaIOError) as e:
        mock_visa.state.set(0)
    for arg in args2:
        assert arg in str(e.value)
    assert mock_visa.state.get() == 0

    mock_visa.state.set(15)
    with pytest.raises(ValueError) as e:
        mock_visa.state.get()
    for arg in args3:
        assert arg in str(e.value)


def test_visa_backend(mocker, request):

    rm_mock = mocker.patch("qcodes.instrument.visa.pyvisa.ResourceManager")

    address_opened = [None]

    class MockBackendVisaInstrument(VisaInstrument):
        visa_handle = MockVisaHandle()

    class MockRM:
        def open_resource(self, address):
            address_opened[0] = address
            return MockVisaHandle()

    rm_mock.return_value = MockRM()

    inst1 = MockBackendVisaInstrument('name', address='None')
    request.addfinalizer(inst1.close)
    assert rm_mock.call_count == 1
    assert rm_mock.call_args == ((),)
    assert address_opened[0] == 'None'
    inst1.close()

    inst2 = MockBackendVisaInstrument('name2', address='ASRL2')
    request.addfinalizer(inst2.close)
    assert rm_mock.call_count == 2
    assert rm_mock.call_args == ((),)
    assert address_opened[0] == 'ASRL2'
    inst2.close()

    inst3 = MockBackendVisaInstrument("name3", address="ASRL3", visalib="@py")
    request.addfinalizer(inst3.close)
    assert rm_mock.call_count == 3
    assert rm_mock.call_args == (("@py",),)
    assert address_opened[0] == "ASRL3"
    inst3.close()


def test_visa_instr_metadata(request):
    metadatadict = {'foo': 'bar'}
    mv = MockVisa('Joe', 'none_adress', metadata=metadatadict)
    request.addfinalizer(mv.close)
    assert mv.metadata == metadatadict


def test_both_visahandle_and_pyvisa_sim_file_raises():

    with pytest.raises(
        RuntimeError,
        match=re.escape(
            "It's an error to supply both visalib and pyvisa_sim_file as arguments to a VISA instrument"
        ),
    ):
        MockVisa(
            name="mock",
            address="nowhere",
            visalib="myfile.yaml@sim",
            pyvisa_sim_file="myfile.yaml",
        )


def test_load_pyvisa_sim_file_implict_module(request):
    from qcodes.instrument_drivers.AimTTi import AimTTiPL601

    driver = AimTTiPL601(
        "AimTTi", address="GPIB::1::INSTR", pyvisa_sim_file="AimTTi_PL601P.yaml"
    )
    request.addfinalizer(driver.close)
    assert driver.visabackend == "sim"
    assert driver.visalib is not None
    path_str, backend = driver.visalib.split("@")
    assert backend == "sim"
    path = Path(path_str)
    assert path.match("qcodes/instrument/sims/AimTTi_PL601P.yaml")


def test_load_pyvisa_sim_file_explicit_module(request):
    from qcodes.instrument_drivers.AimTTi import AimTTiPL601

    driver = AimTTiPL601(
        "AimTTi",
        address="GPIB::1::INSTR",
        pyvisa_sim_file="qcodes.instrument.sims:AimTTi_PL601P.yaml",
    )
    request.addfinalizer(driver.close)
    assert driver.visabackend == "sim"
    assert driver.visalib is not None
    path_str, backend = driver.visalib.split("@")
    assert backend == "sim"
    path = Path(path_str)
    assert path.match("qcodes/instrument/sims/AimTTi_PL601P.yaml")


def test_load_pyvisa_sim_file_invalid_file_raises(request):
    from qcodes.instrument_drivers.AimTTi import AimTTiPL601

    with pytest.raises(
        FileNotFoundError,
        match=re.escape(
            "Pyvisa-sim yaml file could not be found. Trying to load file notafile.yaml from module: qcodes.instrument.sims"
        ),
    ):
        AimTTiPL601(
            "AimTTi",
            address="GPIB::1::INSTR",
            pyvisa_sim_file="qcodes.instrument.sims:notafile.yaml",
        )


def test_load_pyvisa_sim_file_invalid_module_raises(request):
    from qcodes.instrument_drivers.AimTTi import AimTTiPL601

    with pytest.raises(
        ModuleNotFoundError,
        match=re.escape("No module named 'qcodes.instrument.not_a_module'"),
    ):
        AimTTiPL601(
            "AimTTi",
            address="GPIB::1::INSTR",
            pyvisa_sim_file="qcodes.instrument.not_a_module:AimTTi_PL601P.yaml",
        )
