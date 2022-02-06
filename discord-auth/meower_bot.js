import { Cloudlink } from './cloudlink.js';
import { writeFileSync } from 'fs';

globalThis.client = new Cloudlink("wss://server.meower.org");

function uuidv4(){
    var dt = new Date().getTime();
    var uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = (dt + Math.random()*16)%16 | 0;
        dt = Math.floor(dt/16);
        return (c=='x' ? r :(r&0x3|0x8)).toString(16);
    });
    return uuid;
}

function ping() {
    client.send({cmd: "ping", val: ""})
}
setInterval(ping, 10000)

client.on('pmsg', (data) => {
  if (data.val == "auth") {
    var token = String(uuidv4());
    writeFileSync(`${token}.txt`, data.origin);
    client.send({ cmd: "pmsg", id: data.origin, val: token })
  }
});

client.on('connected', () => {
  client.send({ cmd: "direct", val: "meower" })
  client.send({ cmd: "direct", val: { cmd: "authpswd", val: { username: "<MEOWER BOT USERNAME>", pswd: "<MEOWER BOT PASSWORD>" } } })
})

client.on('disconnected', () => {
    process.exit()
})