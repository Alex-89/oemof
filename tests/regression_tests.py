import logging

from nose.tools import eq_, nottest, ok_
import pandas as pd

from oemof.core.energy_system import EnergySystem as ES, Simulation
from oemof.network import Bus
from oemof.outputlib.to_pandas import ResultsDataFrame as RDF
from oemof.solph import (Flow, OperationalModel as OM, Sink, Source as FS,
                         Storage)

class TestSolphAndItsResults:
    def setup(self):
        logging.disable(logging.CRITICAL)

        self.failed = False

        sim = Simulation(timesteps=[0],
                         objective_options={'function': po.minimize_cost})
        tix = time_index = pd.period_range('1970-01-01', periods=1, freq='H')
        self.es = ES(simulation=sim, time_idx=tix)

    # TODO: Fix this test so that it works with the new solph and can be
    #       re-enabled.
    @nottest
    def test_issue_74(self):
        Storage.optimization_options.update({'investment': True})
        bus = Bus(uid="bus")
        store = Storage(uid="store", inputs=[bus], outputs=[bus], c_rate_out=0.1,
                        c_rate_in=0.1)
        sink = Sink(uid="sink", inputs=[bus], val=[1])

        es = self.es
        om = OM(es)
        om.objective.set_value(-1)
        es.results = om.results()

        try:
            es.dump()
        except AttributeError as ae:
            self.failed = ae
        if self.failed:
            ok_(False,
                "EnergySystem#dump should not raise `AttributeError`: \n" +
                " Error message: " + str(self.failed))

    # TODO: Fix this test so that it works with the new solph and can be
    #       re-enabled.
    @nottest
    def test_bus_to_sink_outputs_in_results_dataframe(self):
        bus = Bus(uid="bus")
        source = FS(uid="source", outputs=[bus], val=[0.5], out_max=[1])
        sink = Sink(uid="sink", inputs=[bus], val=[1])

        es = self.es
        om = OM(es)
        es.results = om.results()
        es.results[bus][sink] = [0.7]
        rdf = RDF(energy_system=es)
        try:
            eq_(rdf.loc[(slice(None), slice(None), slice(None), "sink"), :
                       ].val[0],
                0.7,
                "Output from bus to sink does not have the correct value.")
        except KeyError:
            self.failed = True
        if self.failed:
            ok_(False,
                "Output from bus to sink does not appear in results dataframe.")

        es.results[bus][bus] = [-1]
        rdf = RDF(energy_system=es)
        try:
            eq_(rdf.loc[(slice(None), slice(None), slice(None), "sink"), :
                       ].val[0],
                0.7,
                "Output from bus to sink does not have the correct value.")
        except KeyError:
            self.failed = True
        if self.failed:
            ok_(False,
                "Output from bus (with duals) to sink " +
                "does not appear in results dataframe.")

