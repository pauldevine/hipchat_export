# hipchat_exporter

This is a script that will allow you to export your one to one message history from HipChat to files.
This idea was totally forked (stolen) from this [lovely guy](https://github.com/amikeal).

Check out his python version [here](https://github.com/amikeal/hipchat_export).

```
Usage: ruby hipchat_export.rb -t <api_token> -u <user_to_search(defaults to all users)> -v
    -t, --api_token API_TOKEN        API Token for hipchat API
    -u, --user USER                  User to get history for
    -v, --verbose                    Verbose output to std out
```
