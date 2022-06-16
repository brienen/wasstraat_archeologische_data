# timeperiod2daterange
A tool that converts Dutch time period entities to standardised date ranges. 

Usage (direct):

    ./timeperiod2daterange.py

Usage (import into another script)

    import sys
    sys.path.insert(1, 'timeperiod-to-daterange/') # path to folder
    import timeperiod2daterange
    timeperiod2daterange.detection2daterange('1200 n. Chr') # output: [1200, 1200]


Also includes an extended version of the Perio.do time period ontology, in the 'ontologies' folder.
