

## Skipped Design Choices

### A bunch of TODOs in python code

They all denote stuff I planned on implementing but couldn't due to time constraints.

### Encrypting the connection

I initially intended to encrypt the client-server connection, but haven't so far explored the possibility. It's unlikely I'd be able to do it by the submission deadline.

### Client authentication and identity management

Title basically. If implemented this could help leverage certain existing features of the server, like checking whether a certain user has perms to enqueue tasks with a high priority value.

### Logging server events

Colorful, and with verbosity settings. A key feature I missed.

### The Client

As I'd later learn (apologies).

### Better http fetch type task

Using selenium (and maybe even selenium-stealth) for better responses.

## \[SECURITY ISSUE\] Regarding running tasks as processes on the server host

This is inherently unsafe, regardless of whatever amount of sanitization is done on the input.

For instance, simply by specifying a wordlist path in gobuster/ffuf and specifying one's own server as the target server, many files can be arbitrarily read. I considered using solutions like chroot for this, but they are not portable.

It's obvious at this point that I must consider containerization, via Docker (or something more secure, like `nsjail`).
However, that's not portable either, and careful design of the same will require more than a single day.

##### `nmap`

I decided to allow flexible commands from the client, as long as each character of the argument adheres to the regex `[a-zA-Z0-9\-\/\.:,_+=@]`. A (dangerously) quick look at https://gtfobins.github.io/gtfobins/nmap/ suggests that it'd not be all that trivial to exploit given the functionality the server exposes.

##### `gobuster` and `ffuf`

As mentioned earlier, these are more tricky to contain, with just simple regex matching.
For want of time, I am simply settling with a single hardcoded use case:

- "Perform a directory brute-force attack on a given domain (using a tool like
ffuf or gobuster) and return the results."

## Easy Extensibility

I have tried to make the `server` very flexible. As a result, **it is very trivial to add any additional task type** by simply following these two steps:

1. Add an class implementing of `TaskExecutor`, similar to e.g. `EchoExecutor` and `NmapExecutor`.
2. Give the task type a unique name, and append that name to the `EXECUTOR_REGISTRY` variable inside `task_executors.utils.taskutils`.

# Making The Server

## Design Choices and Specification

For developing the first prototype, I abstractd away the specific htmlfetch/nmap/directorybruteforce stuff into a TaskExecutor interface with a default implementation of just using executing the `echo` cli tool (instead of all the hubbub). **Hence, the echo task type (in case you have been wondering)**.

Now comes the meat of it, the specifications:

### The client-server communication

I wanted it to be a custom "protocol" based on TCP (that was obvious).

It could be based on binary suffixes and prefixes, but that'd be difficult to debug or manually test, so I ditched that extra efficiency possibility.
I knew it could be something akin to json-rpc, just a lot simpler, while also allowing binary data which isn't json-encoded to lessen bandwidth wastage.

**The protocol uses JSON messages for requests and responses, with persistent TCP connections for status tracking.**

However, if the server sends a JSON of the form `{"binary_data": <an integer specifying content length, <optionally other properties as metadata> }\n`, then the next `content-length` bytes are to be treated as binary data by the client.

#### Avoiding result loss in case of unreliable connection (i.e. client disconnects)

The server has been designed with this possibility in mind. There are, among others, these `methods` (similar to jsonrpc methods but not that strict on syntax) that the client can use to request info from server (please excuse the undescriptive names, I doubt I will have the time to refactor):
1. `task`: It tells the server to add a task to the queue and start executing it. Returns a server-generated unique task ID immediately (after validation etc).
2. `status` (along with specifying `taskid`): If the task for this taskid is currently either scheduled to run or is running, it subscribes the current connection between the server and the client to the task's stdout and stderr, with periodic resopnses being of the form `{"stdout"|"stderr": "<a utf-8 string if stdout conforms to this format>"|"[Binary Data, size <size of the binary data> bytes" }`. If the task finishes while a client is subscribed to the task, it also automatically sends a `report` response.
3. `watchedtask`: basically `task` followed by `status` method in quick succession.

Note that only a single client can be subscribed to the status of a given running/enqueued task. This behaviour can be changed later if need be.

4. `report`: The server does store the report for every task UNTIL the client consumes it. This is because in this system, it is perfectly valid for clients to not actively listen to updates from the server. They can query the server for the report some time after they scheduled the task for running. Note that the server is currently designed to store the report for a task only until a client consumes it once. This is to prevent excessive unnecessary disk usage on the server (after all the problem statement says it's the client who saves the `result` (which I call `report` here)).
5. `cancel`: The client can cancel any enqueued task which has yet to be started yet.

The tasks support an integer supporting priority.

#### Some vague specification

I am running out of time, so I can't write a full-blown spec right now ~~(without giving my code to some AI based tool and telling it to generate the spec, and going through the pain of correcting it and later realizing you could've written something more accurate in this time, or settling with the somewhat-incorrect but flowery looking spec)~~


**Important:** unlike shown here, each json is sent/received in a single line for ease of communication

```
# Base Request Format (all methods) (all requests other than "keepalive" requests)
{
    "version": 0,              # Currently only version 0 is supported
    "method": "task",          # One of: task, watchedtask, status, report, cancel
    "priority": 0,             # Optional, higher number = higher priority
    "params": {}               # Required for task/watchedtask, format depends on task type
}

# Task Types and Their Parameters:

# 1. Echo Task
{
    "version": 0,
    "method": "task"|"watchedtask",
    "params": {
        "type": "echo",
        "args": [             # Must be array of alphanumeric strings only
            "hello",
            "world"
        ]
    }
}

# 2. Nmap Task
{
    "version": 0,
    "method": "task"|"watchedtask",
    "params": {
        "type": "nmap",
        "args":
            // can be any valid cli args list, the nmap task type is very flexible
            // Example: ["-sP", "172.20.69.0-255"]
    }
    # Note: --stats-every=2s is automatically added if --stats-every isn't already present
}

# 3. Gobuster Task
{
    "version": 0,
    "method": "task"|"watchedtask",
    "params": {
        "type": "gobuster",
        "args": // example: "https://example.com"    // Must be a valid URL
    }
    # Note: -w parameter automatically added with server's configured wordlist
}

# 4. Ffuf Task
{
    "version": 0,
    "method": "task"|"watchedtask",
    "params": {
        "type": "ffuf",
        "args": // example: "https://example.com/FUZZ"    // Must be a valid URL (according to ffuf, i.e. e.g. containing FUZZ)
    }
    # Note: -w parameter automatically added with server's configured wordlist
}

# 5. HTTP fetch task
# TODO add documentation

# URL Validation Rules (for Gobuster/Ffuf):
# - Must start with http:// or https://
# - No fragments (#) allowed
# - No backslashes or semicolons
# - Hostname must be alphanumeric with dots and hyphens only
# - Must match URL format standards

# Task Response
{
    "taskid": // example "ffaf727d-c04d-427d-8c2e-1fba5b4925bc"    # str format
}

# Status Updates (for watchedtask or status subscription)
{
    "time": // Example 1740479033592,     # Unix timestamp in milliseconds
    "stdout": // Example "Progress: 45%"   # Or stderr for error messages
}

# Task Completion Message
{
    "binary_data": // e.g. 1234,       # Size of report file in bytes
    "exit_code": // e.g. 0             # Process exit status
} // THIS IS ALWAYS FOLLOWED BY A BINARY DATA OF LENGTH EXACTLY the length mentioned earlier

# Error Response Format
{
    "error": "Error description message"
}

# Status Request format
{
    "version": 0,
    "method": "status",
    "taskid": // example "550e8400-e29b-41d4-a716-446655440000"
}

# Report Request
{
    "version": 0,
    "method": "report",
    "taskid": // example "550e8400-e29b-41d4-a716-446655440000"
}

# Cancel Request
{
    "version": 0,
    "method": "cancel",
    "taskid": // example "550e8400-e29b-41d4-a716-446655440000"
}
```


##### Components

###### 1. Stellar (Event Loop - Single Threaded) (I just randomly chose to name it "Stellar")  `occupies one of the 5 threads`

I don't want to waste multiple threads on just the client-server communication aspect (because that won't be the bottleneck I believe, unlike http requests which hardly ever introduce long running tasks). So all tracking slots will be handled in that single-threaded event loop singleton itself. This single threaded event loop (Stellar) has a bunch of responsibilities

- Handling all client-server communication and task scheduling

- Parsing and validating requests

- Task management (enqueueing tasks and responding to clients)

- Status subscription (tracking ongoing tasks for clients)

- Receiving status updates from worker threads and forwarding them

- Preventing multiple clients from subscribing to the same task's status



###### 2. Worker Threads `i.e. the other 4 threads`

- Worker threads execute tasks and send periodic status updates to Stellar.

- Each thread picks highest-priority non-cancelled tasks from a thread-safe priority queue.

- Execute instances of the `TaskExecutor` interface

- Outputs from task execution are logged to the final report file and also sent as JSON status updates.


##### Communication

All communication follows a JSON-based protocol over TCP.
Each request is either simply the keepalive payload (`"keepalive"`, yes that's valid json), or the following:
```
{
    "version": 0,
    "method": "task" | "status" | "report" | "watchedtask" | "cancel",
    ...
}
```
(unlike shown here, each json is sent in a single line for simplicity).

**Errors:** All error responses follow this format:
```
{
    "status": "error",
    "error": string     // Error description, chose it to be string for now, planned upon changing it to a more verbose object.
}
```


Please see the implementation for specifics, as I am really running out of time (yet to write the entire client).

### Packaging into a standalone binary using pyinstaller

```sh
# first set up virtual environment if need be
pip install pyinstaller
cd server
pyinstaller --onefile server.py
chmod +x dist/server
dist/server --help
```

# Making The Client

Haven't given it much thought yet, and not much time is left, so I'll make something hopefully stateless, simple and cli based. (GUI in the future 😭).

**UPDATE:** No client before the deadline, sorry. It took quite some time documenting the server itself.
Making a client, however, should be fairly straightforward. That's because I have put a lot of thought designing the server.
The interaction is so simple that a lot of stuff (other than automatically saving the retrieved result on the client side) can be done through netcat itself.
Please check out the [demo videos directory](demo_videos/server).

# Interacting with the server (and verifying some of its functionality) with just netcat

![1.mp4](demo_videos/server/taskexec_server_1.mp4)

![2.mp4](demo_videos/server/taskexec_server_2.mp4)

![3.mp4](demo_videos/server/taskexec_server_3.mp4)
