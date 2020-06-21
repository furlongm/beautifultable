"""This module provides BeautifulTable class

It is intended for printing Tabular data to terminals.

Example
-------
>>> from beautifultable import BeautifulTable
>>> table = BeautifulTable()
>>> table.column_headers = ['1st column', '2nd column']
>>> for i in range(5):
...    table.append_row([i, i*i])
...
>>> print(table)
+------------+------------+
| 1st column | 2nd column |
+------------+------------+
|     0      |     0      |
+------------+------------+
|     1      |     1      |
+------------+------------+
|     2      |     4      |
+------------+------------+
|     3      |     9      |
+------------+------------+
|     4      |     16     |
+------------+------------+
"""
from __future__ import division, unicode_literals

import copy
import csv
import weakref
import operator

from . import enums

from .utils import pre_process, termwidth, textwrap, deprecated, deprecated_param
from .base import BTBaseRow, BTBaseColumn, BTBaseList
from .meta import AlignmentMetaData, NonNegativeIntegerMetaData
from .compat import basestring, Iterable, to_unicode, zip_longest


__all__ = ["BeautifulTable"]


class BTRowData(BTBaseRow):
    def _get_props(self):
        return self._table.columns.alignment, self._table.columns.padding_left, self._table.columns.padding_right

    def _clamp_row(self, row):
        """Process a row so that it is clamped by column_width.

        Parameters
        ----------
        row : array_like
             A single row.

        Returns
        -------
        list of list:
            List representation of the `row` after it has been processed
            according to width exceed policy.
        """
        table = self._table
        _, lpw, rpw = self._get_props()
        wep = table.columns.width_exceed_policy

        result = []

        if (
            wep is enums.WidthExceedPolicy.WEP_STRIP
            or wep is enums.WidthExceedPolicy.WEP_ELLIPSIS
        ):

            # Let's strip the row
            delimiter = "" if wep is enums.WidthExceedPolicy.WEP_STRIP else "..."
            row_item_list = []
            for index, row_item in enumerate(row):
                left_pad = table.columns._pad_character * lpw[index]
                right_pad = table.columns._pad_character * rpw[index]
                clmp_str = (
                    left_pad
                    + self._clamp_string(row_item, index, delimiter)
                    + right_pad
                )
                row_item_list.append(clmp_str)
            result.append(row_item_list)
        elif wep is enums.WidthExceedPolicy.WEP_WRAP:

            # Let's wrap the row
            string_partition = []

            for index, row_item in enumerate(row):
                width = table.columns.width[index] - lpw[index] - rpw[index]
                string_partition.append(textwrap(row_item, width))

            for row_items in zip_longest(*string_partition, fillvalue=""):
                row_item_list = []
                for index, row_item in enumerate(row_items):
                    left_pad = table.columns._pad_character * lpw[index]
                    right_pad = table.columns._pad_character * rpw[index]
                    row_item_list.append(left_pad + row_item + right_pad)
                result.append(row_item_list)

        return [[""] * len(table.columns)] if len(result) == 0 else result

    def _clamp_string(self, row_item, index, delimiter=""):
        """Clamp `row_item` to fit in column referred by index.

        This method considers padding and appends the delimiter if `row_item`
        needs to be truncated.

        Parameters
        ----------
        row_item: str
            String which should be clamped.

        index: int
            Index of the column `row_item` belongs to.

        delimiter: str
            String which is to be appended to the clamped string.

        Returns
        -------
        str
            The modified string which fits in it's column.
        """
        _, lpw, rpw = self._get_props()
        width = self._table.columns.width[index] - lpw[index] - rpw[index]

        if termwidth(row_item) <= width:
            return row_item
        else:
            if width - len(delimiter) >= 0:
                clamped_string = (
                    textwrap(row_item, width - len(delimiter))[0] + delimiter
                )
            else:
                clamped_string = delimiter[:width]
            return clamped_string

    def __str__(self):
        """Return a string representation of a row."""
        rows = []

        table = self._table
        width = table.columns.width
        sign = table.sign_mode

        align, lpw, rpw = self._get_props()

        string = []
        for i, item in enumerate(self._value):
            if isinstance(item, type(table)):
                # temporarily change the max width of the table
                curr_maxwidth = item.maxwidth
                item.maxwidth = width[i] - lpw[i] - rpw[i]
                rows.append(pre_process(item, table.detect_numerics, table.numeric_precision, sign.value).split("\n"))
                item.maxwidth = curr_maxwidth
            else:
                rows.append(pre_process(item, table.detect_numerics, table.numeric_precision, sign.value).split("\n"))
        for row in map(list, zip_longest(*rows, fillvalue="")):
            for i in range(len(row)):
                row[i] = pre_process(
                    row[i],
                    table.detect_numerics,
                    table.numeric_precision,
                    sign.value,
                )
            for row_ in self._clamp_row(row):
                for i in range(len(table.columns)):
                    # str.format method doesn't work for multibyte strings
                    # hence, we need to manually align the texts instead
                    # of using the align property of the str.format method
                    pad_len = width[i] - termwidth(row_[i])
                    if align[i].value == "<":
                        right_pad = " " * pad_len
                        row_[i] = to_unicode(row_[i]) + right_pad
                    elif align[i].value == ">":
                        left_pad = " " * pad_len
                        row_[i] = left_pad + to_unicode(row_[i])
                    else:
                        left_pad = " " * (pad_len // 2)
                        right_pad = " " * (pad_len - pad_len // 2)
                        row_[i] = left_pad + to_unicode(row_[i]) + right_pad
                content = table.column_separator_char.join(row_)
                content = table.left_border_char + content
                content += table.right_border_char
                string.append(content)
        return "\n".join(string)

class BTRowHeader(BTBaseColumn):
    def __init__(self, table, value):
        for i in value:
            self._validate_item(i)
        super(BTRowHeader, self).__init__(table, value)

    def __getitem__(self, key):
        return self._value[key]

    def __setitem__(self, key, value):
        self._validate_item(value)
        if not isinstance(key, int):
            raise TypeError(
                ("header indices must be int, " "not {}").format(
                    type(key).__name__
                )
            )
        self._value[key] = value
    
    def __delitem__(self, key):
        del self._value[key]

    def _validate_item(self, value):
        if not (isinstance(value, basestring) or value is None):
            raise TypeError(
                ("header must be of type 'str', " "got {}").format(
                    type(value).__name__
                )
            )

class BTColumnHeader(BTRowData):
    def __init__(self, table, value):
        for i in value:
            self._validate_item(i)
        self.alignment = None
        super(BTColumnHeader, self).__init__(table, value)
    
    def _get_props(self):
        _, lpw, rpw = super(BTColumnHeader, self)._get_props()
        return (self.alignment, lpw, rpw) if self.alignment else (_, lpw, rpw)

    def __setitem__(self, key, value):
        self._validate_item(value)
        if not isinstance(key, int):
            raise TypeError(
                ("header indices must be int, " "not {}").format(
                    type(key).__name__
                )
            )
        self._value[key] = value

    def _validate_item(self, value):
        if not (isinstance(value, basestring) or value is None):
            raise TypeError(
                ("header must be of type 'str', " "got {}").format(
                    type(value).__name__
                )
            )

class BTTableData(BTBaseList):
    def __init__(self, table, value=None):
        if value is None:
            value = []
        self._table = table
        self._value = value
    
    def _get_canonical_key(self, key):
        return self._table.rows._canonical_key(key)
    
    def _get_ideal_length(self):
        pass

class BTRows(object):
    def __init__(self, table):
        self._table = table
        self._reset_state(0)
    
    @property
    def _table(self):
        return self._table_ref()
    
    @_table.setter
    def _table(self, value):
        self._table_ref = weakref.ref(value)
    
    def _reset_state(self, nrow):
        self._table._data = BTTableData(self._table, BTRowData(self._table, [None]*self._table._ncol)*nrow)
        self.header = BTRowHeader(self._table, [None] * nrow)
    
    @property
    def header(self):
        return self._header

    @header.setter
    def header(self, value):
        self._header = BTRowHeader(self._table, value)
    
    def _canonical_key(self, key):
        if isinstance(key, (int, slice)):
            return key
        elif isinstance(key, basestring):
            return self.header.index(key)
        raise TypeError(
            ("row indices must be int, str or slices, not {}").format(
                type(key).__name__
            )
        )
    
    def __len__(self):
        return len(self._table._data)
    
    def __getitem__(self, key):
        """Get a particular row, or a new table by slicing.

        Parameters
        ----------
        key : int, slice, str
            If key is an `int`, returns a row at index `key`.
            If key is an `str`, returns the first row with heading `key`.
            If key is a slice object, returns a new sliced table.

        Raises
        ------
        TypeError
            If key is not of type int, slice or str.
        IndexError
            If `int` index is out of range.
        KeyError
            If `str` key is not found in header.
        """
        if isinstance(key, slice):
            new_table = copy.copy(self._table)
            new_table._data = BTTableData(new_table)
            for r in self._table._data[key]:
                new_table.rows.append(r.value)
            return new_table
        if isinstance(key, (int, basestring)):
            return self._table._data[key]
        raise TypeError(
            (
                "row indices must be int, str or a slice object, not {}"
            ).format(type(key).__name__)
        )

    def __delitem__(self, key):
        """Delete a row, or multiple rows by slicing.

        Parameters
        ----------
        key : int, slice, str
            If key is an `int`, deletes a row at index `key`.
            If key is an `str`, deletes the first row with heading `key`.
            If key is a slice object, deletes multiple rows.

        Raises
        ------
        TypeError
            If key is not of type int, slice or str.
        IndexError
            If `int` key is out of range.
        KeyError
            If `str` key is not in header.
        """
        if isinstance(key, (int, basestring, slice)):
            del self._table._data[key]
            del self.header[key]
        else:
            raise TypeError(
                (
                    "row indices must be int, str or "
                    "a slice object, not {}"
                ).format(type(key).__name__)
            )

    def __setitem__(self, key, value):
        """Update a row, or multiple rows by slicing.

        Parameters
        ----------
        key : int, slice, str
            If key is an `int`, updates a row.
            If key is an `str`, updates the first row with heading `key`.
            If key is a slice object, updates multiple rows according to slicing
            rules.

        Raises
        ------
        TypeError
            If key is not of type int, slice or str.
        IndexError
            If `int` key is out of range.
        KeyError
            If `str` key is not in header.
        """
        if isinstance(key, (int, basestring)):
            self._table._data[key] = BTRowData(self._table, value)
        elif isinstance(key, slice):
            value = [list(row) for row in value]
            if len(self._table.columns) == 0:
                self._table.columns._initialize(len(value[0]))
            self._table._data[key] = [BTRowData(self._table, row) for row in value]
        else:
            raise TypeError("key must be int, str or a slice object")

    def __contains__(self, key):
        if isinstance(key, basestring):
            return key in self.header
        elif isinstance(key, Iterable):
            return key in self._table._data
        else:
            raise TypeError(
                ("'key' must be str or Iterable, " "not {}").format(
                    type(key).__name__
                )
            )

    def __iter__(self):
        return iter(self._table._data)

    def __next__(self):
        return next(self._table._data)

    def __repr__(self):
        return repr(self._table._data)

    def __str__(self):
        return str(self._table._data)
    
    def reverse(self):
        """Reverse the table row-wise *IN PLACE*."""
        self._table._data._reverse()

    def pop(self, index=-1):
        """Remove and return row at index (default last).

        Parameters
        ----------
        index : int, str
            index or heading of the row. Normal list rules apply.
        """
        if not isinstance(index, (int, basestring)):
            raise TypeError(
                (
                    "row index must be int or str, " "not {}"
                ).format(type(index).__name__)
            )
        if len(self._table._data) == 0:
            raise IndexError("pop from empty table")
        else:
            res = self._table._data._pop(index)
            self.header._pop(index)
            return res

    def insert(self, index, row, header=None):
        """Insert a row before index in the table.

        Parameters
        ----------
        index : int
            List index rules apply

        row : iterable
            Any iterable of appropriate length.
        
        header : str, optional
            Heading of the row

        Raises
        ------
        TypeError:
            If `row` is not an iterable.

        ValueError:
            If size of `row` is inconsistent with the current number
            of columns.
        """
        if self._table._ncol == 0:
            row = list(row)
            self._table.columns._reset_state(len(row))
        self.header._insert(index, header)
        self._table._data._insert(index, BTRowData(self._table, row))

    def append(self, row, header=None):
        """Append a row to end of the table.

        Parameters
        ----------
        row : iterable
            Any iterable of appropriate length.
        
        header : str, optional
            Heading of the row

        """
        self.insert(len(self), row)

    def update(self, key, value):
        """Update row(s) identified with `key` in the table.

        `key` can be a index or a slice object.

        Parameters
        ----------
        key : int or slice
            index of the row, or a slice object.

        value : iterable
            If an index is specified, `value` should be an iterable
            of appropriate length. Instead if a slice object is
            passed as key, value should be an iterable of rows.

        Raises
        ------
        IndexError:
            If index specified is out of range.

        TypeError:
            If `value` is of incorrect type.

        ValueError:
            If length of row does not matches number of columns.
        """
        self[key] = value
    
    def clear(self):
        self._reset_state(0)
    
    def sort(self, key, reverse=False):
        """Stable sort of the table *IN-PLACE* with respect to a column.

        Parameters
        ----------
        key: int, str
            index or header of the column. Normal list rules apply.
        reverse : bool
            If `True` then table is sorted as if each comparison was reversed.
        """
        if isinstance(key, (int, basestring)):
            key = operator.itemgetter(key)
        elif callable(key):
            pass
        else:
            raise TypeError(
                "'key' must either be 'int' or 'str' or a 'callable'"
            )
        self._table._data._sort(key=key, reverse=reverse)
    
    def filter(self, key):
        """Return a copy of the table with only those rows which satisfy a
        certain condition.

        Returns
        -------
        BeautifulTable:
            Filtered copy of the BeautifulTable instance.
        """
        new_table = self._table.copy()
        new_table.rows.clear()
        for row in filter(key, self):
            new_table.rows.append(row)
        return new_table


class BTColumns(object):
    def __init__(self, table, default_alignment, default_padding):
        self._table = table
        self._width_exceed_policy = enums.WEP_WRAP
        self._pad_character = " "
        self.default_alignment = default_alignment
        self.default_padding = default_padding

        self._reset_state(0)
    
    @property
    def _table(self):
        return self._table_ref()
    
    @_table.setter
    def _table(self, value):
        self._table_ref = weakref.ref(value)
    
    @property
    def padding(self):
        raise AttributeError("cannot read attribute 'padding'. use specific padding_{left|right} attribute")

    @padding.setter
    def padding(self, value):
        """Set width for left and rigth padding of the columns of the table.

        Parameters
        ----------
        pad_width : array_like
            pad widths for the columns.
        """
        self.padding_left = value
        self.padding_right = value
    
    def _reset_state(self, ncol):
        self._table._ncol = ncol
        self._header = BTColumnHeader(self._table, [None] * ncol)
        self._alignment = AlignmentMetaData(self._table, [self.default_alignment] * ncol)
        self._width = NonNegativeIntegerMetaData(self._table, [0] * ncol)
        self._padding_left = NonNegativeIntegerMetaData(self._table, [self.default_padding] * ncol)
        self._padding_right = NonNegativeIntegerMetaData(self._table, [self.default_padding] * ncol)
        self._table._data = BTTableData(self._table, BTRowData(self._table, [None]*ncol)*len(self._table._data))
    
    def _canonical_key(self, key):
        if isinstance(key, (int, slice)):
            return key
        elif isinstance(key, basestring):
            return self.header.index(key)
        raise TypeError(
            ("column indices must be int, str or slices, not {}").format(
                type(key).__name__
            )
        )
    
    @property
    def header(self):
        """get/set headings for the columns of the table.

        It can be any iterable having all members an instance of `str` or `NoneType`.
        """
        return self._header

    @header.setter
    def header(self, value):
        self._header = BTColumnHeader(self._table, value)
    
    @property
    def alignment(self):
        """get/set alignment of the columns of the table.

        It can be any iterable containing only the following:

        * beautifultable.ALIGN_LEFT
        * beautifultable.ALIGN_CENTER
        * beautifultable.ALIGN_RIGHT
        """
        return self._alignment

    @alignment.setter
    def alignment(self, value):
        if isinstance(value, enums.Alignment):
            value = [value] * len(self)
        self._alignment = AlignmentMetaData(self._table, value)
    
    @property
    def width(self):
        """get/set width for the columns of the table.

        Width of the column specifies the max number of characters
        a column can contain. Larger characters are handled according to
        the value of `width_exceed_policy`.
        """
        return self._width

    @width.setter
    def width(self, value):
        if isinstance(value, int):
            value = [value] * len(self)
        self._width = NonNegativeIntegerMetaData(self, value)
    
    @property
    def padding_left(self):
        """get/set width for left padding of the columns of the table.

        Left Width of the padding specifies the number of characters
        on the left of a column reserved for padding. By Default It is 1.
        """
        return self._padding_left
    
    @padding_left.setter
    def padding_left(self, value):
        if isinstance(value, int):
            value = [value]*len(self)
        self._padding_left = NonNegativeIntegerMetaData(self, value)
    
    @property
    def padding_right(self):
        """get/set width for right padding of the columns of the table.

        Right Width of the padding specifies the number of characters
        on the rigth of a column reserved for padding. By default It is 1.
        """
        return self._padding_right
    
    @padding_right.setter
    def padding_right(self, value):
        if isinstance(value, int):
            value = [value]*len(self)
        self._padding_right = NonNegativeIntegerMetaData(self, value)
    
    @property
    def width_exceed_policy(self):
        """Attribute to control how exceeding column width should be handled.

        It can be one of the following:

        ============================  =========================================
         Option                        Meaning
        ============================  =========================================
         beautifulbable.WEP_WRAP       An item is wrapped so every line fits
                                       within it's column width.

         beautifultable.WEP_STRIP      An item is stripped to fit in it's
                                       column.

         beautifultable.WEP_ELLIPSIS   An item is stripped to fit in it's
                                       column and appended with ...(Ellipsis).
        ============================  =========================================
        """
        return self._width_exceed_policy

    @width_exceed_policy.setter
    def width_exceed_policy(self, value):
        if not isinstance(value, enums.WidthExceedPolicy):
            allowed = (
                "{}.{}".format(type(self).__name__, i.name)
                for i in enums.WidthExceedPolicy
            )
            error_msg = (
                "allowed values for width_exceed_policy are: "
                + ", ".join(allowed)
            )
            raise ValueError(error_msg)
        self._width_exceed_policy = value

    @property
    def default_alignment(self):
        """Attribute to control the alignment of newly created columns.

        It can be one of the following:

        ============================  =========================================
         Option                        Meaning
        ============================  =========================================
         beautifultable.ALIGN_LEFT     New columns are left aligned.

         beautifultable.ALIGN_CENTER   New columns are center aligned.

         beautifultable.ALIGN_RIGHT    New columns are right aligned.
        ============================  =========================================
        """
        return self._default_alignment

    @default_alignment.setter
    def default_alignment(self, value):
        if not isinstance(value, enums.Alignment):
            allowed = (
                "{}.{}".format(type(self).__name__, i.name)
                for i in enums.Alignment
            )
            error_msg = (
                "allowed values for default_alignment are: "
                + ", ".join(allowed)
            )
            raise ValueError(error_msg)
        self._default_alignment = value

    @property
    def default_padding(self):
        """Initial value for Left and Right padding widths for new columns."""
        return self._default_padding

    @default_padding.setter
    def default_padding(self, value):
        if not isinstance(value, int):
            raise TypeError("default_padding must be an integer")
        elif value <= 0:
            raise ValueError("default_padding must be greater than 0")
        else:
            self._default_padding = value

    def __len__(self):
        return self._table._ncol
    
    def __getitem__(self, key):
        """Get a column, or a new table by slicing.

        Parameters
        ----------

        key : int, slice, str
            If key is an `int`, returns column at index `key`.
            If key is an `str`, returns first column with heading `key`.
            If key is a slice object, returns a new sliced table.

        Raises
        ------

        TypeError
            If key is not of type int, slice or str.
        IndexError
            If `int` key is out of range.
        KeyError
            If `str` key is not in header.
        """
        if isinstance(key, int):
            pass
        elif isinstance(key, slice):
            new_table = copy.copy(self)

            new_table._data = BTTableData(new_table)
            new_table.columns._reset_state(0)
            new_table.columns.header = self.header[key]
            new_table.columns.alignment = self.alignment[key]
            new_table.padding_left = self.padding_left[key]
            new_table.padding_right = self.padding_right[key]
            new_table.width = self.width[key]
            for r in self._table._data:
                new_table.rows.append(r.value[key])
            return new_table
        elif isinstance(key, basestring):
            key = self.header.index(key)
        else:
            raise TypeError(
                (
                    "column indices must be integers, strings or " "slices, not {}"
                ).format(type(key).__name__)
            )
        return (row[key] for row in self._table._data)

    def __delitem__(self, key):
        """Delete a column, or multiple columns by slicing.

        Parameters
        ----------

        key : int, slice, str
            If key is an `int`, deletes column at index `key`.
            If key is a slice object, deletes multiple columns.
            If key is an `str`, deletes the first column with heading `key`

        Raises
        ------

        TypeError
            If key is not of type int, slice or str.
        IndexError
            If `int` key is out of range.
        KeyError
            If `str` key is not in header.
        """
        if isinstance(key, (int, basestring, slice)):
            del self.alignment[key]
            del self.width[key]
            del self.padding_left[key]
            del self.padding_right[key]
            for row in self._table.rows:
                del row[key]
            del self.header[key]
            self._table._ncol = len(self.header)
            if self._table._ncol == 0:
                del self._table.rows[:]
        else:
            raise TypeError(
                (
                    "table indices must be int, str or "
                    "slices, not {}"
                ).format(type(key).__name__)
            )

    def __setitem__(self, key, value):
        """Update a column, or multiple columns by slicing.

        Parameters
        ----------

        key : int, slice, str
            If key is an `int`, updates column at index `key`.
            If key is an `str`, updates first column with heading `key``column`.
            If key is a slice object, updates multiple columns.

        Raises
        ------

        TypeError
            If key is not of type int, slice or str.
        IndexError
            If `int` key is out of range.
        KeyError
            If `str` key is not in header
        """
        if not isinstance(key, (int, basestring, slice)):
            raise TypeError("column indices must be of type int, str or a slice object")
        for row, new_item in zip(self._table.rows, value):
            row[key] = new_item

    def __contains__(self, key):
        if isinstance(key, basestring):
            return key in self.header
        elif isinstance(key, Iterable):
            return key in self._table._data
        else:
            raise TypeError(
                ("'key' must be str or Iterable, " "not {}").format(
                    type(key).__name__
                )
            )

    def __iter__(self):
        return iter(self._table)

    def __next__(self):
        return next(self._table)

    def __repr__(self):
        return repr(self._table)

    def __str__(self):
        return str(self._table._data)
    
    def clear(self):
        self._reset_state(0)

    def pop(self, index=-1):
        """Remove and return column at index (default last).

        Parameters
        ----------
        index : int, str
            index of the column, or the header of the column.
            If index is specified, then normal list rules apply.

        Raises
        ------
        TypeError:
            If index is not an instance of `int`, or `str`.

        IndexError:
            If Table is empty.
        """
        if not isinstance(index, (int, basestring)):
            raise TypeError(
                (
                    "column index must be int or str, " "not {}"
                ).format(type(index).__name__)
            )
        if self._table._ncol == 0:
            raise IndexError("pop from empty table")
        else:
            res = []
            for row in self._table.rows:
                res.append(row._pop(index))
            self.alignment._pop(index)
            self.width._pop(index)
            self.padding_left._pop(index)
            self.padding_right._pop(index)
            self.header._pop(index)

            self._table._ncol = len(self.header)
            if self._table._ncol == 0:
                del self._table.rows[:]
            return res

    def update(self, key, value):
        """Update a column named `header` in the table.

        If length of column is smaller than number of rows, lets say
        `k`, only the first `k` values in the column is updated.

        Parameters
        ----------
        key : int, str
            If `key` is int, column at index `key` is updated.
            If `key` is str, the first column with heading `key` is updated.

        column : iterable
            Any iterable of appropriate length.

        Raises
        ------
        TypeError:
            If length of `column` is shorter than number of rows.

        ValueError:
            If no column exists with heading `header`.
        """
        self[key] = value

    def insert(self, index, column, header=None):
        """Insert a column before `index` in the table.

        If length of column is bigger than number of rows, lets say
        `k`, only the first `k` values of `column` is considered.
        If column is shorter than 'k', ValueError is raised.

        Note that Table remains in consistent state even if column
        is too short. Any changes made by this method is rolled back
        before raising the exception.

        Parameters
        ----------
        index : int
            List index rules apply.
        
        column : iterable
            Any iterable of appropriate length.

        header : str, optional
            Heading of the column.

        Raises
        ------
        TypeError:
            If `header` is not of type `str`.

        ValueError:
            If length of `column` is shorter than number of rows.
        """
        if self._table._ncol == 0:
            self.header = [header]
            self._table._data = [BTRowData(self._table, [i]) for i in column]
        else:
            if not isinstance(header, basestring):
                raise TypeError("header must be of type str")
            column_length = 0
            for row, new_item in zip(self._table.rows, column):
                row._insert(index, new_item)
                column_length += 1
            if column_length == len(self._table.rows):
                self._table._ncol += 1
                self.header._insert(index, header)
                self.width._insert(index, 0)
                self.alignment._insert(index, self.default_alignment)
                self.padding_left._insert(index, self.default_padding)
                self.padding_right._insert(index, self.default_padding)
            else:
                # Roll back changes so that table remains in consistent state
                for j in range(column_length, -1, -1):
                    self._table.rows[j]._pop(index)
                raise ValueError(
                    (
                        "length of 'column' should be atleast {}, " "got {}"
                    ).format(len(self._table.rows), column_length)
                )

    def append(self, column, header=None):
        """Append a column to end of the table.

        Parameters
        ----------
        header : str, optional
            Heading of the column

        column : iterable
            Any iterable of appropriate length.
        """
        self.insert(self._table._ncol, column, header)


class BeautifulTable(object):
    """Utility Class to print data in tabular format to terminal.
    The instance attributes can be used to customize the look of the
    table. To disable a behaviour, just set its corresponding attribute
    to an empty string. For example, if Top border should not be drawn,
    set `top_border_char` to ''.

    Parameters
    ----------
    max_width: int, optional
        maximum width of the table in number of characters. this is ignored
        when manually setting the width of the columns. if this value is too
        low with respect to the number of columns and width of padding, the
        resulting table may override it(default 80).
    
    default_alignment : int, optional
        Default alignment for new columns(default beautifultable.ALIGN_CENTER).
    
    default_padding : int, optional
        Default width of the left and right padding for new columns(default 1).
    
    Attributes
    ----------

    left_border_char : str
        Character used to draw the left border.

    right_border_char : str
        Character used to draw the right border.

    top_border_char : str
        Character used to draw the top border.

    bottom_border_char : str
        Character used to draw the bottom border.

    header_separator_char : str
        Character used to draw the line seperating Header from data.

    row_separator_char : str
        Character used to draw the line seperating two rows.

    column_separator_char : str
        Character used to draw the line seperating two columns.

    intersection_char : str
        Character used to draw intersection of a vertical and horizontal
        line. Disabling it just draws the horizontal line char in it's place.
        (DEPRECATED).

    intersect_top_left : str
        Left most character of the top border.

    intersect_top_mid : str
        Intersection character for top border.

    intersect_top_right : str
        Right most character of the top border.

    intersect_header_left : str
        Left most character of the header separator.

    intersect_header_mid : str
        Intersection character for header separator.

    intersect_header_right : str
        Right most character of the header separator.

    intersect_row_left : str
        Left most character of the row separator.

    intersect_row_mid : str
        Intersection character for row separator.

    intersect_row_right : str
        Right most character of the row separator.

    intersect_bottom_left : str
        Left most character of the bottom border.

    intersect_bottom_mid : str
        Intersection character for bottom border.

    intersect_bottom_right : str
        Right most character of the bottom border.

    numeric_precision : int
        All float values will have maximum number of digits after the decimal,
        capped by this value(Default 3).

    serialno : bool
        Whether automatically generated serial number should be printed for
        each row(Default False).

    serialno_header : str
        The header of the autogenerated serial number column. This value is
        only used if serialno is True(Default SN).

    detect_numerics : bool
        Whether numeric strings should be automatically detected(Default True).
    """

    @deprecated_param('1.0.0', '1.2.0', 'max_width', 'maxwidth')
    def __init__(
        self,
        maxwidth=80,
        default_alignment=enums.ALIGN_CENTER,
        default_padding=1,
        numeric_precision=3,
        serialno=False,
        serialno_header="SN",
        detect_numerics=True,
        sign_mode=enums.SM_MINUS,
        **kwargs
    ):

        kwargs.setdefault('max_width', None)
        if kwargs['max_width'] is not None:
            maxwidth = kwargs['max_width']

        self.set_style(enums.STYLE_DEFAULT)

        self.numeric_precision = numeric_precision
        self.serialno = serialno
        self.serialno_header = serialno_header
        self.detect_numerics = detect_numerics

        self._sign_mode = enums.SM_MINUS
        self.maxwidth = maxwidth

        self._ncol = 0
        self._data = BTTableData(self)

        self.rows = BTRows(self)
        self.columns = BTColumns(self, default_alignment, default_padding)
    
    def __copy__(self):
        obj = type(self)()
        obj.__dict__.update({k: copy.copy(v) for k,v in self.__dict__.items()})
        
        obj.rows._table = obj
        obj.columns._table = obj
        for row in obj._data:
            row._table = obj
        
        return obj
    
    def __deepcopy__(self, memo):
        obj = type(self)()
        obj.__dict__.update({k: copy.deepcopy(v, memo) for k,v in self.__dict__.items()})

        obj.rows._table = obj
        obj.columns._table = obj
        for row in obj._data:
            row._table = obj
        
        return obj

    def __setattr__(self, name, value):
        attrs = (
            "left_border_char",
            "right_border_char",
            "top_border_char",
            "bottom_border_char",
            "header_separator_char",
            "column_separator_char",
            "row_separator_char",
            "intersect_top_left",
            "intersect_top_mid",
            "intersect_top_right",
            "intersect_header_left",
            "intersect_header_mid",
            "intersect_header_right",
            "intersect_row_left",
            "intersect_row_mid",
            "intersect_row_right",
            "intersect_bottom_left",
            "intersect_bottom_mid",
            "intersect_bottom_right",
        )
        if to_unicode(name) in attrs and not isinstance(value, basestring):
            value_type = type(value).__name__
            raise TypeError(
                (
                    "Expected {attr} to be of type 'str', " "got '{attr_type}'"
                ).format(attr=name, attr_type=value_type)
            )
        super(BeautifulTable, self).__setattr__(name, value)
    
    def __len__(self):
        return len(self.rows)
    
    def __iter__(self):
        return iter(self.rows)
    
    def __next(self):
        return next(self.rows)
    
    def __contains__(self, key):
        if isinstance(key, basestring):
            return key in self.columns
        elif isinstance(key, Iterable):
            return key in self.rows
        else:
            raise TypeError(
                ("'key' must be str or Iterable, " "not {}").format(
                    type(key).__name__
                )
            )
    
    def __repr__(self):
        return repr(self._data)
    
    def __str__(self):
        return self.get_string()

    # ************************Properties Begin Here************************

    @property
    def sign_mode(self):
        """Attribute to control how signs are displayed for numerical data.

        It can be one of the following:

        ========================  =============================================
         Option                    Meaning
        ========================  =============================================
         beautifultable.SM_PLUS    A sign should be used for both +ve and -ve
                                   numbers.

         beautifultable.SM_MINUS   A sign should only be used for -ve numbers.

         beautifultable.SM_SPACE   A leading space should be used for +ve
                                   numbers and a minus sign for -ve numbers.
        ========================  =============================================
        """
        return self._sign_mode

    @sign_mode.setter
    def sign_mode(self, value):
        if not isinstance(value, enums.SignMode):
            allowed = (
                "{}.{}".format(type(self).__name__, i.name)
                for i in enums.SignMode
            )
            error_msg = "allowed values for sign_mode are: " + ", ".join(
                allowed
            )
            raise ValueError(error_msg)
        self._sign_mode = value
    
    @property
    def maxwidth(self):
        """get/set the maximum width of the table.

        The width of the table is guaranteed to not exceed this value. If it
        is not possible to print a given table with the width provided, this
        value will automatically adjust.
        """
        offset = (len(self.columns) - 1) * termwidth(
            self.column_separator_char
        )
        offset += termwidth(self.left_border_char)
        offset += termwidth(self.right_border_char)
        self._maxwidth = max(
            self._maxwidth, offset + len(self.columns)
        )
        return self._maxwidth
    
    @maxwidth.setter
    def maxwidth(self, value):
        self._maxwidth = value
    
    @property
    @deprecated('1.0.0', '1.2.0', maxwidth.fget)
    def max_table_width(self):
        return self.maxwidth
    
    @max_table_width.setter
    @deprecated('1.0.0', '1.2.0', maxwidth.fget)
    def max_table_width(self, value):
        self.maxwidth = value
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.__len__, details="Use 'len(self.columns)' instead.")
    def column_count(self):
        return len(self.columns)
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.width_exceed_policy.fget)
    def width_exceed_policy(self):
        return self.columns.width_exceed_policy

    @width_exceed_policy.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.width_exceed_policy.fget)
    def width_exceed_policy(self, value):
        self.columns.width_exceed_policy = value

    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.default_alignment.fget)
    def default_alignment(self):
        return self.columns.default_alignment

    @default_alignment.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.default_alignment.fget)
    def default_alignment(self, value):
        self.columns.default_alignment = value

    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.default_padding.fget)
    def default_padding(self):
        return self.columns.default_padding

    @default_padding.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.default_padding.fget)
    def default_padding(self, value):
        self.columns.default_padding = value
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.width.fget)
    def column_widths(self):
        return self.columns.width

    @column_widths.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.width.fget)
    def column_widths(self, value):
        self.columns.width = value
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.header.fget)
    def column_headers(self):
        return self.columns.header

    @column_headers.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.header.fget)
    def column_headers(self, value):
        self.columns.header = value
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.alignment.fget)
    def column_alignments(self):
        return self.columns.alignment

    @column_alignments.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.alignment.fget)
    def column_alignments(self, value):
        self.columns.alignment = value
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.padding_left.fget)
    def left_padding_widths(self):
        return self.columns.padding_left

    @left_padding_widths.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.padding_left.fget)
    def left_padding_widths(self, value):
        self.columns.padding_left = value
    
    @property
    @deprecated('1.0.0', '1.2.0', BTColumns.padding_right.fget)
    def right_padding_widths(self):
        return self.columns.padding_right

    @right_padding_widths.setter
    @deprecated('1.0.0', '1.2.0', BTColumns.padding_right.fget)
    def right_padding_widths(self, value):
        self.columns.padding_right = value

    @deprecated('1.0.0', '1.2.0', BTColumns.__getitem__, details="Use 'BeautifulTable.{columns|rows}[key]' instead.")
    def __getitem__(self, key):
        if isinstance(key, basestring):
            return self.columns[key]
        return self.rows[key]
    
    @deprecated('1.0.0', '1.2.0', BTColumns.__setitem__, details="Use 'BeautifulTable.{columns|rows}[key]' instead.")
    def __setitem__(self, key, value):
        if isinstance(key, basestring):
            self.columns[key] = value
        else:
            self.rows[key] = value
    
    @deprecated('1.0.0', '1.2.0', BTColumns.__delitem__, details="Use 'BeautifulTable.{columns|rows}[key]' instead.")
    def __delitem__(self, key):
        if isinstance(key, basestring):
            del self.columns[key]
        else:
            del self.rows[key]
    
    # *************************Properties End Here*************************
    
    @deprecated('1.0.0', '1.2.0', BTColumns.__getitem__, details="Use 'BeautifulTable.columns[key]' instead.")
    def get_column(self, key):
        return self.columns[key]
    
    @deprecated('1.0.0', '1.2.0', BTColumnHeader.__getitem__, details="Use 'BeautifulTable.columns.header[key]' instead.")
    def get_column_header(self, index):
        return self.columns.header[index]
    
    @deprecated('1.0.0', '1.2.0', BTColumnHeader.__getitem__, details="Use 'BeautifulTable.columns.header.index(header)' instead.")
    def get_column_index(self, header):
        return self.columns.header.index(header)
    
    @deprecated('1.0.0', '1.2.0', BTRows.filter)
    def filter(self, key):
        return self.rows.filter(key)
    
    @deprecated('1.0.0', '1.2.0', BTRows.sort)
    def sort(self, key, reverse=False):
        self.rows.sort(key, reverse=reverse)
    
    @deprecated('1.0.0', '1.2.0', BTRows.reverse)
    def reverse(self, value):
        self.rows.reverse()
    
    @deprecated('1.0.0', '1.2.0', BTRows.pop)
    def pop_row(self, index=-1):
        return self.rows.pop(index)
    
    @deprecated('1.0.0', '1.2.0', BTRows.insert)
    def insert_row(self, index, row):
        return self.rows.insert(index, row)
    
    @deprecated('1.0.0', '1.2.0', BTRows.append)
    def append_row(self, value):
        self.rows.append(value)
    
    @deprecated('1.0.0', '1.2.0', BTRows.update)
    def update_row(self, key, value):
        self.rows.update(key, value)
    
    @deprecated('1.0.0', '1.2.0', BTColumns.pop)
    def pop_column(self, index=-1):
        return self.columns.pop(index)
    
    @deprecated('1.0.0', '1.2.0', BTColumns.insert)
    def insert_column(self, index, header, column):
        self.columns.insert(index, column, header)
    
    @deprecated('1.0.0', '1.2.0', BTColumns.append)
    def append_column(self, header, column):
        self.columns.append(column, header)
    
    @deprecated('1.0.0', '1.2.0', BTColumns.update)
    def update_column(self, header, column):
        self.columns.update(header, column)

    def set_style(self, style):
        """Set the style of the table from a predefined set of styles.

        Parameters
        ----------
        style: Style

            It can be one of the following:

            * beautifultable.STYLE_DEFAULT
            * beautifultable.STYLE_NONE
            * beautifultable.STYLE_DOTTED
            * beautifultable.STYLE_MYSQL
            * beautifultable.STYLE_SEPARATED
            * beautifultable.STYLE_COMPACT
            * beautifultable.STYLE_MARKDOWN
            * beautifultable.STYLE_RESTRUCTURED_TEXT
            * beautifultable.STYLE_BOX
            * beautifultable.STYLE_BOX_DOUBLED
            * beautifultable.STYLE_BOX_ROUNDED
            * beautifultable.STYLE_GRID
        """
        if not isinstance(style, enums.Style):
            allowed = (
                "{}.{}".format(type(self).__name__, i.name)
                for i in enums.Style
            )
            error_msg = "allowed values for style are: " + ", ".join(allowed)
            raise ValueError(error_msg)
        style_template = style.value
        self.left_border_char = style_template.left_border_char
        self.right_border_char = style_template.right_border_char
        self.top_border_char = style_template.top_border_char
        self.bottom_border_char = style_template.bottom_border_char
        self.header_separator_char = style_template.header_separator_char
        self.column_separator_char = style_template.column_separator_char
        self.row_separator_char = style_template.row_separator_char
        self.intersect_top_left = style_template.intersect_top_left
        self.intersect_top_mid = style_template.intersect_top_mid
        self.intersect_top_right = style_template.intersect_top_right
        self.intersect_header_left = style_template.intersect_header_left
        self.intersect_header_mid = style_template.intersect_header_mid
        self.intersect_header_right = style_template.intersect_header_right
        self.intersect_row_left = style_template.intersect_row_left
        self.intersect_row_mid = style_template.intersect_row_mid
        self.intersect_row_right = style_template.intersect_row_right
        self.intersect_bottom_left = style_template.intersect_bottom_left
        self.intersect_bottom_mid = style_template.intersect_bottom_mid
        self.intersect_bottom_right = style_template.intersect_bottom_right

    def _calculate_width(self):
        """Calculate width of column automatically based on data."""
        table_width = self.width
        lpw, rpw = self.columns.padding_left, self.columns.padding_right
        pad_widths = [(lpw[i] + rpw[i]) for i in range(len(self.columns))]
        maxwidths = [0 for index in range(len(self.columns))]
        offset = table_width - sum(self.columns.width) + sum(pad_widths)
        self._maxwidth = max(
            self._maxwidth, offset + len(self.columns)
        )

        for index, header in enumerate(self.columns.header):
            max_length = 0
            for i in pre_process(header, self.detect_numerics, self.numeric_precision, self.sign_mode.value).split("\n"):
                output_str = pre_process(
                    i,
                    self.detect_numerics,
                    self.numeric_precision,
                    self.sign_mode.value,
                )
                max_length = max(max_length, termwidth(output_str))
            maxwidths[index] += max_length

        for index, column in enumerate(zip(*self._data)):
            max_length = maxwidths[index]
            for i in column:
                for j in pre_process(i, self.detect_numerics, self.numeric_precision, self.sign_mode.value).split("\n"):
                    output_str = pre_process(
                        j,
                        self.detect_numerics,
                        self.numeric_precision,
                        self.sign_mode.value,
                    )
                    max_length = max(max_length, termwidth(output_str))
            maxwidths[index] = max_length

        sum_ = sum(maxwidths)
        desired_sum = self._maxwidth - offset

        # Set flag for columns who are within their fair share
        temp_sum = 0
        flag = [0] * len(maxwidths)
        for i, width in enumerate(maxwidths):
            if width <= int(desired_sum / len(self.columns)):
                temp_sum += width
                flag[i] = 1
            else:
                # Allocate atleast 1 character width to the column
                temp_sum += 1

        avail_space = desired_sum - temp_sum
        actual_space = sum_ - temp_sum
        shrinked_columns = {}

        # Columns which exceed their fair share should be shrinked based on
        # how much space is left for the table
        for i, width in enumerate(maxwidths):
            self.columns.width[i] = width
            if not flag[i]:
                new_width = 1 + int((width - 1) * avail_space / actual_space)
                if new_width < width:
                    self.columns.width[i] = new_width
                    shrinked_columns[new_width] = i

        # Divide any remaining space among shrinked columns
        if shrinked_columns:
            extra = self._maxwidth - offset - sum(self.columns.width)
            actual_space = sum(shrinked_columns)

            if extra > 0:
                for i, width in enumerate(sorted(shrinked_columns)):
                    index = shrinked_columns[width]
                    extra_width = int(width * extra / actual_space)
                    self.columns.width[i] += extra_width
                    if i == (len(shrinked_columns) - 1):
                        extra = (
                            self._maxwidth
                            - offset
                            - sum(self.columns.width)
                        )
                        self.columns.width[index] += extra

        for i in range(len(self.columns)):
            self.columns.width[i] += pad_widths[i]
    
    @deprecated('1.0.0', '1.2.0', BTColumns.padding.fget)
    def set_padding_widths(self, pad_width):
        self.columns.padding_left = pad_width
        self.columns.padding_right = pad_width

    def copy(self):
        """Return a shallow copy of the table.

        Returns
        -------
        BeautifulTable:
            shallow copy of the BeautifulTable instance.
        """
        return copy.copy(self)
    
    @deprecated_param('1.0.0', '1.2.0', 'clear_metadata', 'reset_columns')
    def clear(self, reset_columns=False, **kwargs):
        """Clear the contents of the table.

        Clear all rows of the table, and if specified clears all column
        specific data.

        Parameters
        ----------
        reset_columns : bool, optional
            If it is true(default False), all metadata of columns such as their
            alignment, padding, width, etc. are also cleared and number of
            columns is set to 0.
        """
        kwargs.setdefault('clear_metadata', None)
        if kwargs['clear_metadata']:
            reset_columns = kwargs['clear_metadata']
        self.rows.clear()
        if reset_columns:
            self.columns.clear()

    def _get_horizontal_line(
        self, char, intersect_left, intersect_mid, intersect_right
    ):
        """Get a horizontal line for the table.

        Internal method used to draw all horizontal lines in the table.
        Column width should be set prior to calling this method. This method
        detects intersection and handles it according to the values of
        `intersect_*_*` attributes.

        Parameters
        ----------
        char : str
            Character used to draw the line.

        Returns
        -------
        str
            String which will be printed as a line in the table.
        """
        width = self.width

        try:
            line = list(char * (int(width / termwidth(char)) + 1))[:width]
        except ZeroDivisionError:
            line = [" "] * width

        if len(line) == 0:
            return ""

        # Only if Special Intersection is enabled and horizontal line is
        # visible
        if not char.isspace():
            # If left border is enabled and it is visible
            visible_junc = not intersect_left.isspace()
            if termwidth(self.left_border_char) > 0:
                if not (self.left_border_char.isspace() and visible_junc):
                    length = min(
                        termwidth(self.left_border_char),
                        termwidth(intersect_left),
                    )
                    for i in range(length):
                        line[i] = intersect_left[i]
            visible_junc = not intersect_right.isspace()
            # If right border is enabled and it is visible
            if termwidth(self.right_border_char) > 0:
                if not (self.right_border_char.isspace() and visible_junc):
                    length = min(
                        termwidth(self.right_border_char),
                        termwidth(intersect_right),
                    )
                    for i in range(length):
                        line[-i - 1] = intersect_right[-i - 1]
            visible_junc = not intersect_mid.isspace()
            # If column separator is enabled and it is visible
            if termwidth(self.column_separator_char):
                if not (self.column_separator_char.isspace() and visible_junc):
                    index = termwidth(self.left_border_char)
                    for i in range(len(self.columns) - 1):
                        index += self.columns.width[i]
                        length = min(
                            termwidth(self.column_separator_char),
                            termwidth(intersect_mid),
                        )
                        for j in range(length):
                            line[index + j] = intersect_mid[j]
                        index += termwidth(self.column_separator_char)

        return "".join(line)

    def _get_top_border(self):
        return self._get_horizontal_line(
            self.top_border_char,
            self.intersect_top_left,
            self.intersect_top_mid,
            self.intersect_top_right,
        )

    def _get_header_separator(self):
        return self._get_horizontal_line(
            self.header_separator_char,
            self.intersect_header_left,
            self.intersect_header_mid,
            self.intersect_header_right,
        )

    def _get_row_separator(self):
        return self._get_horizontal_line(
            self.row_separator_char,
            self.intersect_row_left,
            self.intersect_row_mid,
            self.intersect_row_right,
        )

    def _get_bottom_border(self):
        return self._get_horizontal_line(
            self.bottom_border_char,
            self.intersect_bottom_left,
            self.intersect_bottom_mid,
            self.intersect_bottom_right,
        )
    
    @property
    def width(self):
        """Get the actual width of the table as number of characters.

        Column width should be set prior to calling this method.

        Returns
        -------
        int
            Width of the table as number of characters.
        """
        if len(self.columns) == 0:
            return 0
        width = sum(self.columns.width)
        width += (len(self.columns) - 1) * termwidth(
            self.column_separator_char
        )
        width += termwidth(self.left_border_char)
        width += termwidth(self.right_border_char)
        return width
    
    @deprecated('1.0.0', '1.2.0', width.fget)
    def get_table_width(self):
        return self.width

    def _get_string(self, rows, append=False, recalculate_width=False):
        # Rendering the top border
        if self.serialno:
            if len(self.columns) > 0:
                self.columns.insert(
                    0, range(1, len(self) + 1), self.serialno_header
                )

        if recalculate_width or sum(self.columns.width) == 0:
            self._calculate_width()

        if self.serialno:
            if len(self.columns) > 0 and self.columns.width[0] == 0:
                self.columns.width[0] = (
                    max(4, len(self.serialno_header))
                    + 2 * self.columns.default_padding
                )

        if self.top_border_char:
            yield self._get_top_border()

        # Print headers if not empty or only spaces
        if "".join(x if x is not None else '' for x in self.columns.header).strip():
            header = to_unicode(self.columns.header)
            yield header

            if self.header_separator_char:
                yield self._get_header_separator()

        # Printing rows
        first_row_encountered = False
        for row in self.rows:
            if first_row_encountered and self.row_separator_char:
                yield self._get_row_separator()
            first_row_encountered = True
            content = to_unicode(row)
            yield content

        prev_length = len(self.rows)
        for i, row in enumerate(rows, start=1):
            if first_row_encountered and self.row_separator_char:
                yield self._get_row_separator()
            first_row_encountered = True
            if self.serialno:
                row.insert(0, prev_length + i)
            self.rows.append(row)
            content = to_unicode(self.rows[-1])
            if not append:
                self.rows.pop()
            yield content

        # Rendering the bottom border
        if self.bottom_border_char:
            yield self._get_bottom_border()

        if self.serialno and len(self.columns) > 0:
            self.columns.pop(0)

    def stream(self, rows, append=False):
        """Get a generator for the table.

        This should be used in cases where data takes time to retrieve and
        it is required to be displayed as soon as possible. Any existing rows
        in the table shall also be returned. It is essential that atleast one
        of title, width or existing rows set prior to calling this method.

        Parameters
        ----------
        rows : iterable
            A generator which yields one row at a time.

        append : bool, optional
            If rows should also be appended to the table.(Default False)

        Returns
        -------
        iterable:
            string representation of the table as a generators
        """
        for line in self._get_string(
            rows, append=append, recalculate_width=False
        ):
            yield line

    def get_string(self, recalculate_width=True):
        """Get the table as a String.

        Parameters
        ----------
        recalculate_width : bool, optional
            If width for each column should be recalculated(default True).
            Note that width is always calculated if it wasn't set
            explicitly when this method is called for the first time ,
            regardless of the value of `recalculate_width`.

        Returns
        -------
        str:
            Table as a string.
        """

        if len(self.rows) == 0:
            return ""

        string_ = []
        for line in self._get_string(
            [], append=False, recalculate_width=recalculate_width
        ):
            string_.append(line)

        return "\n".join(string_)

    def to_csv(self, file_name, *args, **kwargs):
        """Export table to CSV format.

        Parameters
        ----------
        file_name : str
            Path to CSV file.
        """

        if not isinstance(file_name, str):
            raise ValueError(
                ("Expected 'file_name' to be string, got {}").format(
                    type(file_name).__name__
                )
            )

        with open(file_name, mode="wt", newline="") as csv_file:
            csv_writer = csv.writer(
                csv_file, *args, **kwargs
            )
            csv_writer.writerow(self.columns.header)  # write header
            csv_writer.writerows(self.rows)  # write table

    def from_csv(self, file_name, header=True, **kwargs):
        """Create table from CSV file.

        Parameters
        ----------
        file_name : str
            Path to CSV file.
        header : bool, optional
            Whether First row in CSV file should be parsed as table header.

        Raises
        ------
        ValueError
            If `file_name` is not str type.
        FileNotFoundError
            If `file_name` is not valid path to file.
        """

        if not isinstance(file_name, str):
            raise ValueError(
                ("Expected 'file_name' to be string, got {}").format(
                    type(file_name).__name__
                )
            )

        with open(file_name, mode="rt", newline="") as csv_file:
            csv_reader = csv.reader(csv_file, **kwargs)

            if header:
                self.columns.header = next(csv_reader)

            for row in csv_reader:
                self.rows.append(row)

            return self
