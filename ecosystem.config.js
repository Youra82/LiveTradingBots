module.exports = {
  apps : [{
    name   : "envelope-bot",
    script : "/home/ubuntu/LiveTradingBots/start_bot.sh", // <-- HIER DIE ÄNDERUNG
    watch: false,
    autorestart: true,
    max_memory_restart: '200M'
    // Die "interpreter"-Zeile wird komplett entfernt!
  }]
};
