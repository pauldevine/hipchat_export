require 'net/http'
require 'uri'
require 'json'
require 'optparse'

@options = {
  :api_token => nil,
  :user => nil,
}

OptionParser.new do |opts|

  opts.banner = "Usage: ruby hipchat_export.rb -t <api_token>"

  opts.on('-t', '--api_token API_TOKEN', 'API Token for hipchat API') do |v|
    @options[:api_token] = v
  end

  opts.on('-u', '--user USER', 'User to get history for') do |v|
    @options[:user] = v
  end

end.parse!

raise "must pass api token" if @options[:api_token].nil?

EXPORT_DIR = "./exported_chats"
Dir.mkdir(EXPORT_DIR) unless File.exists?(EXPORT_DIR)

def make_request(url)
  req = Net::HTTP::Get.new(url)
  req.add_field('Authorization', "Bearer #{@options[:api_token]}")
  res = Net::HTTP.start(url.host, url.port, :use_ssl => url.scheme == 'https') do |http|
    http.request(req)
  end
  return res
end

def get_users()
  res = make_request(URI.parse("https://api.hipchat.com/v2/user"))
  check_for_rate_limit(res.code)
  response = JSON.parse(res.body)
  users = []
  if @options[:user].nil?
    response['items'].each { |user|
      users.push({'id' => user['id'], 'name' => user['name']})
    }
  else
    response['items'].each { |user|
      users.push({'id' => user['id'], 'name' => user['name']}) if @options[:user] == user['name']
    } 
  end
  if users.nil? || users.empty?
    puts "user you are looking for doesnt exist or their name is spelled wrong."
    exit 1
  end
  return users
end

def get_history(users)
  users.each { |user|
    file_name = "#{EXPORT_DIR}/#{user['name']}.txt"
    next_page = true
    date = Time.now.to_i
    url = URI.parse("https://api.hipchat.com/v2/user/#{user['id']}/history?date=#{date}&max-results=1000")
    while next_page
      res = make_request(url)
      check_for_rate_limit(res.code)
      response = JSON.parse(res.body)
      messages = ''
      next if response['items'].nil? || response['items'].nil?
      puts "Getting message history for #{user['name']}"
      create_file(file_name)
      response['items'].each { |message|
        messages << message['date'] + " - " + message['message'] + "\n"
      }
      write_messages(file_name, messages)
      if response['links']['next'].nil?
        next_page = false
      else
        url = URI.parse(response['links']['next'])
      end
    end
  }
end

def check_for_rate_limit(code)
  if code.to_i == 429
    take_5(310)
  end
end

def create_file(file)
  unless File.exist?(file)
    File.write(file, "")
  end
end

def write_messages(file, messages)
  hist_file = File.open(file, 'a')
  hist_file.puts messages
  hist_file.close
end

def take_5(reset)
  sleepy_time = reset
  puts "\nYou have been rate limited by hipchats wonderful API service. Sleeping for #{sleepy_time} seconds to reset the API limit."
  while sleepy_time != 0
    sleep 1
    print "#{sleepy_time} seconds remaining..." + "\r"
    $stdout.flush unless sleepy_time == 1
    sleepy_time -= 1
  end
  puts "\nNaptimes over, lets get cracking.\n\n"
end

users = get_users()
get_history(users)
puts "Export complete, please check #{EXPORT_DIR} for all your history files."