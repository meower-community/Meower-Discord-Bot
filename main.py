from flask import Flask, request, make_response, render_template
import requests
import os
import json
import time
app = Flask(__name__, static_url_path='')

global webhook
webhook = "<webhook URL>"

@app.route("/")
def index():
  return "Landing page coming soon!"

@app.route("/discord-auth")
def discord_auth():
  if request.args.get('id'):
    with open("discord-auth/users/id.json", 'r') as f:
      data = json.loads(f.read())
      if request.args.get('id') in data.keys():
        UserID = data[request.args.get('id')]["ID"]
        Username = data[request.args.get('id')]["username"]
        if data[request.args.get('id')]["timestamp"] < int(time.time()):
          del data[request.args.get('id')]
          with open("discord-auth/users/id.json", 'w') as f:
            json.dump(data, f, indent=4)
          return render_template("discord-auth.html", error="This verification ID has expired - Please retry verification")
      else:
        return render_template("discord-auth.html", error="Invalid ID or Token - Please retry verification")
    return render_template("discord-auth.html", user=Username, error=None)
  else:
    return render_template("discord-auth.html", error="Invalid ID or Token - Please retry verification")

@app.route("/discord-verify")
def discord_verify():
  if request.args.get('id') and request.args.get('token'):
    with open("discord-auth/users/id.json", 'r') as f:
      data = json.loads(f.read())
      if request.args.get('id') in data.keys():
        UserID = data[request.args.get('id')]["ID"]
        if data[request.args.get('id')]["timestamp"] < int(time.time()):
          del data[request.args.get('id')]
          with open("discord-auth/users/id.json", 'w') as f:
            json.dump(data, f, indent=4)
          return render_template("discord-auth.html", error="This verification ID has expired - Please retry verification")
        else:
          del data[request.args.get('id')]
          with open("discord-auth/users/id.json", 'w') as f:
            json.dump(data, f, indent=4)
      else:
        return render_template("discord-auth.html", error="Invalid ID or Token - Please retry verification")
    try:
      try:
        with open(f"discord-auth/{request.args.get('token')}.txt", 'r') as f:
          meower_user = f.read()
      except:
        return render_template("discord-auth.html", error="Invalid ID or Token - Please retry verification")
      with open("discord-auth/users/meower.json", 'r') as f:
        meower_users = json.loads(f.read())
      if meower_user in meower_users.keys():
        request_data = {
          "username": "DiscordAuth",
          "content": f"0;{meower_users[meower_user]};{meower_user}"
        }
        requests.post(webhook, data=request_data)
      request_data = {
        "username": "DiscordAuth",
        "content": f"1;{UserID};{meower_user}"
      }
      requests.post(webhook, data=request_data)
      os.remove(f"discord-auth/{request.args.get('token')}.txt")
      return render_template("discord-auth-success.html")
    except :
      return render_template("discord-auth.html", error="Internal error - Please alert Tnix about this")
  else:
    return render_template("discord-auth.html", error="Invalid ID or Token - Please retry verification")

if __name__ == "__main__":
  app.run("0.0.0.0", 80)
