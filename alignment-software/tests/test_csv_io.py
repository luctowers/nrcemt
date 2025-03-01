import os
from tempfile import TemporaryDirectory
import tempfile

import numpy as np
import pytest

from alignment_software.engine.csv_io import (
    load_marker_csv, read_columns_csv, read_single_column_csv,
    write_columns_csv, write_marker_csv, write_single_column_csv
)

dirname = os.path.dirname(__file__)
marker_filename = os.path.join(dirname, 'resources/marker_data.csv')


def test_load_marker_csv():
    markers = load_marker_csv(marker_filename)
    assert markers.shape == (5, 61, 2)
    np.testing.assert_equal(markers[0][0], [534, 851])
    np.testing.assert_equal(markers[0][1], [529, 850])
    np.testing.assert_equal(markers[0][2], [519, 850])
    np.testing.assert_equal(markers[1][0], [443, 726])


def test_write_marker_csv():
    markers = load_marker_csv(marker_filename)
    with tempfile.TemporaryDirectory() as tempdir:
        csvfilename = os.path.join(tempdir, "test.csv")
        write_marker_csv(csvfilename, markers)
        reloaded_markers = load_marker_csv(csvfilename)
    np.testing.assert_array_equal(reloaded_markers, markers)


def test_read_write_columns_csv():
    with TemporaryDirectory() as tempdir:
        with pytest.raises(FileNotFoundError):
            read_columns_csv(os.path.join(tempdir, "foo.csv"), ["x"])
        csvfilename = os.path.join(tempdir, "test.csv")
        write_columns_csv(
            csvfilename,
            {
                "x": [1, 2, 3],
                "y": [4, 5, 6],
                "z": [7, 8, 9, 10]
            }
        )
        assert read_columns_csv(csvfilename, ["x"])["x"] == [1, 2, 3]
        assert read_columns_csv(csvfilename, ["y"])["y"] == [4, 5, 6]
        assert read_columns_csv(csvfilename, ["z"])["z"] == [7, 8, 9, 10]
        assert read_columns_csv(csvfilename, ["y", "z"]) == {
            "y": [4, 5, 6],
            "z": [7, 8, 9, 10]
        }
        assert read_columns_csv(csvfilename, ["x", "z"]) == {
            "x": [1, 2, 3],
            "z": [7, 8, 9, 10]
        }
        write_columns_csv(
            csvfilename,
            {
                "y": [42, "abc"]
            }
        )
        assert read_columns_csv(csvfilename, ["x", "y", "z"]) == {
            "x": [1, 2, 3],
            "y": [42, "abc"],
            "z": [7, 8, 9, 10]
        }


def test_read_write_single_column_csv():
    with TemporaryDirectory() as tempdir:
        with pytest.raises(FileNotFoundError):
            read_columns_csv(os.path.join(tempdir, "foo.csv"), ["x"])
        csvfilename = os.path.join(tempdir, "test.csv")
        write_single_column_csv(csvfilename, [1, 2, 3, 5, 6, 42])
        assert read_single_column_csv(csvfilename) == [1, 2, 3, 5, 6, 42]
        write_single_column_csv(csvfilename, [77])
        assert read_single_column_csv(csvfilename) == [77]
