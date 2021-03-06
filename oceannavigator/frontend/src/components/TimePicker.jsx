import React from "react";
import $ from "jquery";
/*eslint no-unused-vars: ["error", {"varsIgnorePattern": "jQuery" }]*/
import jQuery from "jquery";
import dateFormat from "dateformat";
import {Button} from "react-bootstrap";
import Icon from "./Icon.jsx";

import "jquery-ui-css/base.css";
import "jquery-ui-css/datepicker.css";
import "jquery-ui-css/theme.css";
import "jquery-ui/datepicker";
import "jquery-ui/button";
import "jquery-ui-month-picker/MonthPicker.css";
import "jquery-ui-month-picker/MonthPicker.js";
import "jquery-ui/../i18n/datepicker-fr.js";
import "jquery-ui/../i18n/datepicker-fr-CA.js";

var i18n = require("../i18n.js");

class TimePicker extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      data: [],
      map: {},
      revmap: {},
      times: [],
    };
    $.datepicker.setDefaults($.datepicker.regional[i18n.language]);
  }
  populate(props) {
    if ("url" in props && "" != props.url) {
      $.ajax({
        url: props.url,
        dataType: "json",
        cache: false,
        success: function(data) {
          var map = {};
          var revmap = {};
          var min = 0;
          var max = data.length - 1;
          if (props.hasOwnProperty("min")) {
            min = parseInt(props.min) + 1;
            if (min < 0) {
              min += data.length;
            }
          }
          if (props.hasOwnProperty("max")) {
            max = parseInt(props.max) - 1;
            if (max < 0) {
              max += data.length;
            }
          }
          for (var d in data) {
            var d1 = new Date(data[d].value);
            var d2 = new Date(d1.getTime() + d1.getTimezoneOffset() * 60000);
            var d3 = d2;
            if (this.props.quantum != "hour") {
              d3 = new Date(Date.UTC(
                                d1.getUTCFullYear(),
                                d1.getUTCMonth(),
                                d1.getUTCDate(),
                                0, 0, 0, 0
                            ));
            }
            map[data[d].id] = d2;
            revmap[d3.toUTCString()] = data[d].id;
          }
          this.setState({
            data: data,
            map: map,
            revmap: revmap,
            min: min,
            max: max,
          }, function() {
            switch(props.quantum) {
              case "month":
                $(this.refs.picker).MonthPicker({
                  Button: false,
                  MonthFormat: "MM yy",
                  OnAfterMenuClose: this.pickerChange.bind(this),
                  MinMonth: new Date(
                    map[min].getTime() + 
                    map[min].getTimezoneOffset() * 60 * 1000
                  ),
                  MaxMonth: new Date(
                    map[max].getTime() +
                    map[max].getTimezoneOffset() * 60 * 1000
                  ),
                  i18n: {
                    year: _("Year"),
                    prevYear: _("Previous Year"),
                    nextYear: _("Next Year"),
                    next12Years: _("Jump Forward 12 Years"),
                    prev12Years: _("Jump Back 12 Years"),
                    nextLabel: _("Next"),
                    prevLabel: _("Prev"),
                    buttonText: _("Open Month Chooser"),
                    jumpYears: _("Jump Years"),
                    backTo: _("Back to"),
                    months: [
                      _("Jan."), _("Feb."), _("Mar."), _("Apr."), _("May"),
                      _("June"), _("July"), _("Aug."), _("Sep."), _("Oct."),
                      _("Nov."), _("Dec.")
                    ]
                  }
                });
                break;
              case "day":
                $(this.refs.picker).datepicker( {
                  Button: false,
                  dateFormat: "dd MM yy",
                  onClose: this.pickerChange.bind(this),
                  minDate: new Date(map[min]),
                  maxDate: new Date(map[max]),
                });

                $(this.refs.picker).datepicker(
                  "option",
                  "minDate",
                  new Date(map[min])
                );
                $(this.refs.picker).datepicker(
                  "option",
                  "maxDate",
                  new Date(map[max])
                );
                break;
              case "hour":
                $(this.refs.picker).datepicker({
                  Button: false,
                  dateFormat: "dd MM yy",
                  onClose: this.pickerChange.bind(this),
                  minDate: new Date(map[min]),
                  maxDate: new Date(map[max]),
                });
                $(this.refs.picker).datepicker(
                  "option",
                  "minDate",
                  new Date(map[min])
                );
                $(this.refs.picker).datepicker(
                  "option",
                  "maxDate",
                  new Date(map[max])
                );
                break;
            }
            this.pickerChange();

          }.bind(this));
        }.bind(this),
        error: function(xhr, status, err) {
          console.error(props.url, status, err.toString());
        }.bind(this)
      });
    }
  }
  componentDidMount() {
    this.populate(this.props);
  }
  componentWillReceiveProps(nextProps) {
    if (nextProps.url != this.props.url ||
            nextProps.min != this.props.min ||
            nextProps.max != this.props.max) {
      this.populate(nextProps);
    }
  }
  pickerChange() {
    var min = 0;
    var max = -1;
    if (this.props.hasOwnProperty("min")) {
      min = parseInt(this.props.min) + 1;
    }
    if (this.props.hasOwnProperty("max")) {
      max = parseInt(this.props.max) - 1;
    }
    if (min < 0) {
      min += this.state.data.length;
    }
    if (max < 0) {
      max += this.state.data.length;
    }

    var d;
    if (this.props.quantum == "hour") {
      var times = [];
      d = $(this.refs.picker).datepicker("getDate");
      var isodatestr = dateFormat(d, "yyyy-mm-dd");
      for (var i in this.state.data) {
        if (this.state.data[i].value.indexOf(isodatestr) == 0) {
          if (this.state.data[i].id <= max && this.state.data[i].id >= min) {
            times.unshift({
              id: this.state.data[i].id,
              value: dateFormat(this.state.map[i], "HH:MM")
            });
          }
        }
      }
      this.setState({
        times: times,
      });
      if (times.length > 0) {
        if (this.state.value === undefined) {
          this.props.onUpdate(this.props.id, times[0].id);
        } else if (
          this.state.data[this.props.state].value.indexOf(isodatestr) != 0
        ) {
          this.props.onUpdate(this.props.id, times[0].id);
        }

      }
    } else if (this.refs.picker != null) {
      if (
        this.props.quantum == "month" &&
        $.data(this.refs.picker, "KidSysco-MonthPicker")
      ) {
        d = $(this.refs.picker).MonthPicker("GetSelectedDate");
      } else {
        d = $(this.refs.picker).datepicker("getDate");
      }
      if (d != null) {
        var utcDate = new Date(Date.UTC(
                    d.getFullYear(),
                    d.getMonth(),
                    (this.props.quantum == "month") ? 15 : d.getDate(),
                    d.getHours(),
                    d.getMinutes(),
                    d.getSeconds(),
                    d.getMilliseconds()
                ));
        this.props.onUpdate(
          this.props.id,
          this.state.revmap[utcDate.toUTCString()]
        );
      } else {
        if (this.props.state < 0) {
          this.props.onUpdate(
            this.props.id,
            this.state.data.length + this.props.state
          );
        }
      }
    }
  }
  timeChange(e) {
    var value = e.target.value;
    this.setState({
      value: value
    });
    this.props.onUpdate(this.props.id, value);
  }
  nextTime() {
    var value = parseInt(this.props.state) + 1;
    this.props.onUpdate(this.props.id, value);
    this.setState({
      value: value
    }, function() {
      this.updatePicker(value - 1, value);
    }.bind(this));
  }
  prevTime() {
    var value = parseInt(this.props.state) - 1;
    this.setState({
      value: value
    }, function() {
      this.updatePicker(value + 1, value);
    }.bind(this));
    this.props.onUpdate(this.props.id, value);
  }
  updatePicker(oldstate, newstate) {
    if (this.state.data[oldstate].value.substring(0, 10) !=
      this.state.data[newstate].value.substring(0, 10)) {
      this.pickerChange();
    }
  }
  isFirstTime() {
    return parseInt(this.props.state) == this.state.min;
  }
  isLastTime() {
    return parseInt(this.props.state) == this.state.max;
  }
  render() {
    var date;
    var value = parseInt(this.props.state);

    if (value < 0) {
      value += this.state.data.length;
    }

    if (value < 0) {
      value = 0;
    }

    date = new Date(this.state.map[value]);
    var input = "";
    switch(this.props.quantum) {
      case "month":
        input = <input
          readOnly
          ref='picker'
          type="text"
          value={$.datepicker.formatDate("MM yy", date)}
        />;
        break;
      case "day":
      case "hour":
        input = <input
          readOnly
          ref='picker'
          type="text"
          value={$.datepicker.formatDate("dd MM yy", date)}
        />;
        break;
    }

    var timeinput = "";
    var options = this.state.times.map(function (t) {
      return (
        <option key={t.id} value={t.id}>
          {t.value}
        </option>
      );
    });
    if (this.props.quantum == "hour") {
      timeinput = <select
        value={this.state.value}
        onChange={this.timeChange.bind(this)}>
        {options}
      </select>;
    }

    return (
      <div key={this.props.url} className='TimePicker input'>
        <h1>{this.props.title}</h1>

        <div>
          <Button
            onClick={() => this.prevTime()}
            disabled={this.isFirstTime()}
          ><Icon icon='caret-left' alt="<" /></Button>
          <div>
            {input}
            {timeinput}
          </div>
          <Button
            onClick={() => this.nextTime()}
            disabled={this.isLastTime()}
          ><Icon icon='caret-right' alt=">" /></Button>
        </div>
      </div>
    );
  }
}

export default TimePicker;
