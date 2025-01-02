"""Module to define DataLoader class."""

from collections import OrderedDict
from copy import deepcopy
from logging import Logger
from typing import List, Optional
from lakehouse_engine.algorithms.algorithm import Algorithm
from lakehouse_engine.utils.logging_handler import LoggingHandler
from lakehouse_engine.io.reader_factory import ReaderFactory
from lakehouse_engine.io.writer_factory import WriterFactory
from lakehouse_engine.core.definitions import (
    InputSpec,
    OutputSpec,
    OutputFormat,
)

class DataLoader(Algorithm):
    """Load data using an algorithm configuration (ACON represented as dict).

    This algorithm focuses on the cases where users will be specifying all the algorithm
    steps and configurations through a dict based configuration, which we name ACON
    in our framework.

    Since an ACON is a dict you can pass a custom transformer through a python function
    and, therefore, the DataLoader can also be used to load data with custom
    transformations not provided in our transformers package.

    As the algorithm base class of the lakehouse-engine framework is based on the
    concept of ACON, this DataLoader algorithm simply inherits from Algorithm,
    without overriding anything. We designed the codebase like this to avoid
    instantiating the Algorithm class directly, which was always meant to be an
    abstraction for any specific algorithm included in the lakehouse-engine framework.
    """

    def __init__(self, acon: dict):
        """Construct DataLoader algorithm instances.

        A data loader needs several specifications to work properly,
        but some of them might be optional. The available specifications are:

        - input specifications (mandatory): specify how to read data.
        - transform specifications (optional): specify how to transform data.
        - data quality specifications (optional): specify how to execute the data
            quality process.
        - output specifications (mandatory): specify how to write data to the
            target.
        - terminate specifications (optional): specify what to do after writing into
            the target (e.g., optimizing target table, vacuum, compute stats, etc).

        Args:
            acon: algorithm configuration.
        """
        self._logger: Logger = LoggingHandler(self.__class__.__name__).get_logger()
        super().__init__(acon)
        self.input_specs: List[InputSpec] = self._get_input_specs()
        self.output_specs: List[OutputSpec] = self._get_output_specs()

    def _get_input_specs(self) -> List[InputSpec]:
        """Get the input specifications from an acon.

        Returns:
            List of input specifications.
        """
        return [InputSpec(**spec) for spec in self.acon["input_specs"]]

    def _get_output_specs(self) -> List[OutputSpec]:
        """Get the output specifications from an acon.

        Returns:
            List of output specifications.
        """
        return [
            OutputSpec(
                spec_id=spec["spec_id"],
                input_id=spec["input_id"],
                write_type=spec.get("write_type", None),
                data_format=spec.get("data_format", OutputFormat.DELTAFILES.value),
                db_table=spec.get("db_table", None),
                location=spec.get("location", None),
                partitions=spec.get("partitions", [])
            )
            for spec in self.acon["output_specs"]
        ]

    def read(self) -> OrderedDict:
        """Read data from an input location into a distributed dataframe.

        Returns:
             An ordered dict with all the dataframes that were read.
        """
        read_dfs: OrderedDict = OrderedDict({})
        for spec in self.input_specs:
            self._logger.info(f"Found input specification: {spec}")
            read_dfs[spec.spec_id] = ReaderFactory.get_data(spec)
        return read_dfs

    def write(self, data: OrderedDict) -> OrderedDict:
        """Write the data that was read and transformed (if applicable).

        It supports writing multiple datasets. However, we only recommend to write one
        dataframe. This recommendation is based on easy debugging and reproducibility,
        since if we start mixing several datasets being fueled by the same algorithm, it
        would unleash an infinite sea of reproducibility issues plus tight coupling and
        dependencies between datasets. Having said that, there may be cases where
        writing multiple datasets is desirable according to the use case requirements.
        Use it accordingly.

        Args:
            data: dataframes that were read and transformed (if applicable).

        Returns:
            Dataframes that were written.
        """
        written_dfs: OrderedDict = OrderedDict({})
        for spec in self.output_specs:
            self._logger.info(f"Found output specification: {spec}")

            written_output = WriterFactory.get_writer(
                spec, data[spec.input_id], data
            ).write()
            if written_output:
                written_dfs.update(written_output)
            else:
                written_dfs[spec.spec_id] = data[spec.input_id]

        return written_dfs

    def execute(self) -> Optional[OrderedDict]:
        """Define the algorithm execution behaviour."""
        try:
            self._logger.info("Starting read stage...")
            read_dfs = self.read()
            print(read_dfs)
            self._logger.info("Starting write stage...")
            written_dfs = self.write(read_dfs)
            self._logger.info("Execution of the algorithm has finished!")
        except Exception as e:
            raise e

        return written_dfs
