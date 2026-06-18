"""Knowledge-graph ontology (node and edge type constants)."""

from __future__ import annotations


class NodeType:
    JUNCTION = "Junction"
    ROAD = "Road"
    SIGNAL = "Signal"
    INCIDENT = "Incident"
    WEATHER = "Weather"
    EVENT = "Event"
    VEHICLE = "Vehicle"
    VIOLATION = "Violation"
    ACCIDENT = "Accident"


class EdgeType:
    FROM = "FROM"  # Road -> Junction (origin)
    TO = "TO"  # Road -> Junction (destination)
    CONTROLS = "CONTROLS"  # Signal -> Junction
    OCCURRED_ON = "OCCURRED_ON"  # Incident/Violation/Accident -> Road
    NEAR = "NEAR"  # Event -> Junction
    AFFECTS = "AFFECTS"  # Weather/Incident -> Junction/Road
    DURING = "DURING"  # Event -> (time) (modelled via props)
    CAUSED_BY = "CAUSED_BY"  # Junction congestion -> cause
