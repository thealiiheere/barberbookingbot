// PM2 config - an alternative to the systemd unit in this same folder.
// PM2 works on both Linux and Windows and doesn't need root access,
// which makes it convenient for quick deployments or Windows servers.
//
// SETUP (requires Node.js + npm installed):
//   npm install -g pm2
//
// START THE BOT:
//   pm2 start deploy/ecosystem.config.js
//
// USEFUL COMMANDS:
//   pm2 status                 # is it running?
//   pm2 logs barber-bot        # live logs (in addition to logs/bot.log)
//   pm2 restart barber-bot     # restart manually
//   pm2 stop barber-bot
//
// MAKE IT SURVIVE A SERVER REBOOT (Linux):
//   pm2 startup      # follow the printed instructions once
//   pm2 save         # after the bot is running, saves this as the boot list
//
// If the bot process crashes, PM2 restarts it automatically within
// milliseconds (that's the whole point of using a process manager).

module.exports = {
  apps: [
    {
      name: "barber-bot",
      script: "main.py",
      interpreter: "python3",
      // If you're using a virtualenv, point this at its python instead, e.g.:
      // interpreter: "/home/barberbot/barber_bot/.venv/bin/python",
      cwd: __dirname + "/..",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      watch: false,
    },
  ],
};