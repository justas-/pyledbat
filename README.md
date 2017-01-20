# pyledbat

Low Extra Delay Background Transport (LEDBAT) implementation written in Python3.

This repository contains an implementation of LEDBAT protocol and a program to test the implementation. 

## Library

LEDBAT protocol implementation is split into 2 parts. The “BaseLedbat” class implements the LEDBAT protocol as described in [RFC6817](https://tools.ietf.org/html/rfc6817). Congestion timeout calculation is implemented as described in [RFC6298](https://tools.ietf.org/html/rfc6298). While the “BaseLedbat” class can be used on its own, it can also be extended to implement data-gating. As an example, “SwiftLedbat” implements data-gating as it is done in the [Libswift](https://github.com/libswift/libswift).

## Test application

The LEDBAT library is accompanied by a test program. The purpose of the test program is to send data as fast as possible while using LEDBAT as congestion control mechanism. To run the test program, you will need two hosts. In one of the hosts run the test app as:

`python3 testapp.py`

In the second host run test app as:

`python3 testapp.py --role=client --remote=<IP of the first host>`

The test application will run until it is stopped by issuing Ctrl-C command. The test results will be printed in the console window. This application works on Windows and Linux. It might work in other OS’es as well. You can get more verbose output by adding "--debug" command-line parameter.

For those using [Python Tools for Visual Studio](https://github.com/Microsoft/PTVS), solution and project files are provided in the repository.

##Contributing

All contributions (bug reports, fixes, pull-requests) are welcome.
