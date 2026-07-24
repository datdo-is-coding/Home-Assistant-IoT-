import fetch from '@system.fetch';
import vibrator from '@system.vibrator';

export default {
  data: {
    power: "0",
    voltage: "0.0",
    current: "0.00",
    evnCost: "0",
    loadText: "NORMAL",
    loadClass: "normal-load",
    isConnected: false,
    isHighLoad: false,
    phoneIp: "192.168.4.1", // IP phone or ESP32
    timerId: null
  },

  onInit() {
    this.fetchData();
    this.timerId = setInterval(() => {
      this.fetchData();
    }, 2000);
  },

  onDestroy() {
    if (this.timerId) {
      clearInterval(this.timerId);
    }
  },

  fetchData() {
    let self = this;
    fetch.fetch({
      url: 'http://' + self.phoneIp + '/data',
      method: 'GET',
      responseType: 'json',
      success: function(response) {
        if (response && response.data) {
          let data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
          self.isConnected = true;
          self.power = data.power || "0";
          self.voltage = data.voltage || "0.0";
          self.current = data.current || "0.00";
          self.evnCost = data.money ? parseInt(data.money).toLocaleString() : "0";

          let p = parseFloat(self.power) || 0;
          if (p > 2000) {
            self.loadText = "HIGH LOAD";
            self.loadClass = "high-load";
            if (!self.isHighLoad) {
              self.isHighLoad = true;
              self.triggerVibration();
            }
          } else if (p > 800) {
            self.loadText = "MEDIUM LOAD";
            self.loadClass = "medium-load";
            self.isHighLoad = false;
          } else {
            self.loadText = "NORMAL LOAD";
            self.loadClass = "normal-load";
            self.isHighLoad = false;
          }
        }
      },
      fail: function() {
        self.isConnected = false;
      }
    });
  },

  triggerVibration() {
    vibrator.vibrate({
      mode: 'long',
      success: function() {},
      fail: function() {}
    });
  },

  dismissWarning() {
    this.isHighLoad = false;
  }
}
