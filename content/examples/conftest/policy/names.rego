package main

import future.keywords.contains
import future.keywords.if

deny contains msg if {
	forbidden_names := ["john"]
    
    name := input.users[_].name
	name == forbidden_names[_]
    
    msg := sprintf("username %v is not allowed", [name])
}

warn contains msg if {    
    id := input.users[_].id
	id == 2
    
    msg := sprintf("id %v is not allowed", [id])
}

