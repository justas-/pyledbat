# pyledbat

Low Extra Delay Background Transport (LEDBAT) implementation written in Python3.

This repository contains an implementation of LEDBAT protocol and a program to test the implementation. 

## Library

LEDBAT protocol implementation is split into 2 parts. The “BaseLedbat” class implements the LEDBAT protocol as described in [RFC6817](https://tools.ietf.org/html/rfc6817). In order to actually use the implementation, it must be extended with Congestion Timeout / Round-trip-time (RTT) calculation and data gating functions. This is done in "SimpleLedbat" class. It implements CTO/RTT calculation as described in [RFC6298](https://tools.ietf.org/html/rfc6298). Data gating is done by calling `try_sending(SZ_DATA)` function returning a tuple in form `(can_send, reason)`. Boolean `can_send` parameter indicates if data can be sent now. If data should not be sent (`can_send == False`), integer `reason` parameter will indicate the reason (either in congetion timeout (1) or congestion window is too small(2)).

An alternative (and better) gating method could return a time interval in second when the next try to send should be made. This value could be derived from the congestion interval length (if in congestion), or congestion window size and RTT time (if CWND is too small).

## Test application

The LEDBAT library is accompanied by a test program. The purpose of the test program is to send data as fast as possible while using LEDBAT as congestion control mechanism. To run the test program, you will need two hosts. In one of the hosts run the test app as:

`python3 testapp.py`

In the second host run test app as:

`python3 testapp.py --role=client --remote=<IP of the first host>`

The test application will run until it is stopped by issuing Ctrl-C command. The test results will be printed in the console window. This application works on Windows and Linux. It might work in other OS’es as well. The test application working in the client mode supports several other options which can be listed by calling the application with `-h` argument. At the time of writing, the supported options were:

* `--role {client|server}` Run client in the given mode. Server ignores all other options
* `--remote <IP Address>` IP Address of the LEDBAT test application running in the server mode
* `--makelog` Save various application runtime values into CSV file
* `--log-name <Name>` Name of the log file. By default it is UnixTime-RemoteIP-RemotePort.csv
* `--log-dir <Name>` Path to the directory where the log file should be saved
* `--time <NSec>` Run client for indicated number of seconds before exiting
* `--parallel <N>` Run indicated number of parallel data transfers
* `--ledbat-set-target <ms>` Set the LEDBAT target delay to the indicated value (ms)
* `--ledbat-set-allowed-increase <N>` Set the LEDBAT CWND growth parameters (Allowed_Increase) to the indicated value

For those using [Python Tools for Visual Studio](https://github.com/Microsoft/PTVS), solution and project files are provided in the repository.

##Contributing

All contributions (bug reports, fixes, pull-requests) are welcome.
