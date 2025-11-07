import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from database import get_school_normalized


def handle_temporal_query(ast_node: Dict[str, Any], default_field: str = 'law_school_year') -> Dict[str, Any]:
    """
    Handle temporal queries and determine which year field to use.
    
    Args:
        ast_node: AST node with temporal query
        default_field: Default field to use (law_school_year or undergrad_year)
        
    Returns:
        Modified AST node with correct field
    """
    field = ast_node.get('field', default_field)
    
    # If field is already specified, use it
    if field in ['law_school_year', 'undergrad_year']:
        return ast_node
    
    # Default to law_school_year for "graduated" queries
    if 'graduated' in str(ast_node.get('value', '')).lower() or field == 'graduated':
        ast_node['field'] = default_field
    
    return ast_node


def compile_ast_to_sql(ast: List[Dict[str, Any]], conn: sqlite3.Connection) -> Tuple[str, List[Any]]:
    """
    Compile AST to parameterized SQL query.
    
    Args:
        ast: AST representation of query
        conn: Database connection for lookups
        
    Returns:
        Tuple of (SQL query string, parameter list)
    """
    if not ast:
        # Default query: return all lawyers
        return "SELECT DISTINCT l.id, l.name, l.url FROM lawyers l", []
    
    # Build WHERE clause
    where_parts = []
    params = []
    joins = set()
    fts_joins = set()  # Track FTS5 joins separately
    is_first_condition = True
    
    i = 0
    while i < len(ast):
        node = ast[i]
        
        # Handle boolean operators
        if node.get('op') in ['AND', 'OR', 'NOT']:
            if node['op'] == 'AND':
                where_parts.append('AND')
            elif node['op'] == 'OR':
                where_parts.append('OR')
            elif node['op'] == 'NOT':
                where_parts.append('NOT')
            i += 1
            is_first_condition = False
            continue
        
        # Handle field queries
        field = node.get('field')
        op = node.get('op')
        value = node.get('value')
        
        if not field or not op:
            i += 1
            continue
        
        condition = None
        
        # Name queries - use FTS5 for whole-word matching
        if field == 'name':
            fts_joins.add('lawyers_fts')
            # Split value into words for proper FTS5 matching
            name_words = str(value).strip().split()
            
            if op == 'contains':
                # Use FTS5 MATCH for whole-word matching
                # FTS5 matches whole words by default, so "alon" won't match "Malone"
                # Join words with AND for multi-word names (all words must match)
                fts_query = ' '.join(name_words)
                condition = "fts.full_name MATCH ?"
                params.append(fts_query)
            elif op == 'eq':
                # Exact match - use phrase match in FTS5
                fts_query = '"' + str(value) + '"'
                condition = "fts.full_name MATCH ?"
                params.append(fts_query)
        
        # Title queries
        elif field == 'title':
            if op == 'eq':
                condition = "l.title = ?"
                params.append(value)
            elif op == 'contains':
                condition = "l.title LIKE ?"
                params.append(f"%{value}%")
        
        # School queries
        elif field == 'school':
            joins.add('educations')
            # Normalize school name
            normalized = get_school_normalized(conn, str(value))
            if op == 'contains':
                condition = "(e.school_name LIKE ? OR e.school_normalized LIKE ?)"
                params.append(f"%{value}%")
                params.append(f"%{normalized}%")
            elif op == 'eq':
                condition = "(e.school_name = ? OR e.school_normalized = ?)"
                params.append(value)
                params.append(normalized)
        
        # Temporal queries (graduation year)
        elif field in ['law_school_year', 'undergrad_year', 'graduated']:
            joins.add('educations')
            node = handle_temporal_query(node, 'law_school_year')
            year_field = 'law_school_year' if 'law' in node.get('field', '') else 'undergrad_year'
            
            if op == 'gt':
                condition = "e.year > ? AND e.is_law_degree = 1"
                params.append(value)
            elif op == 'lt':
                condition = "e.year < ? AND e.is_law_degree = 1"
                params.append(value)
            elif op == 'gte':
                condition = "e.year >= ? AND e.is_law_degree = 1"
                params.append(value)
            elif op == 'lte':
                condition = "e.year <= ? AND e.is_law_degree = 1"
                params.append(value)
            elif op == 'eq':
                condition = "e.year = ? AND e.is_law_degree = 1"
                params.append(value)
        
        # Practice queries
        elif field == 'practice':
            joins.add('practices')
            if op == 'eq':
                condition = "p.practice_type = ?"
                params.append(value)
            elif op == 'contains':
                condition = "p.practice_type LIKE ?"
                params.append(f"%{value}%")
        
        # Industry queries
        elif field == 'industry':
            joins.add('industries')
            if op == 'eq':
                condition = "ind.industry = ?"
                params.append(value)
            elif op == 'contains':
                condition = "ind.industry LIKE ?"
                params.append(f"%{value}%")
        
        # Region queries
        elif field == 'region':
            joins.add('regions')
            if op == 'eq':
                condition = "r.region = ?"
                params.append(value)
            elif op == 'contains':
                condition = "r.region LIKE ?"
                params.append(f"%{value}%")
        
        # Language queries
        elif field == 'language':
            joins.add('languages')
            if op == 'eq':
                # Use case-insensitive matching for languages
                condition = "LOWER(lang.language) = LOWER(?)"
                params.append(value)
            elif op == 'contains':
                # Use case-insensitive LIKE matching
                condition = "LOWER(lang.language) LIKE LOWER(?)"
                params.append(f"%{value}%")
        
        if condition:
            # Add AND before condition if not the first one and no explicit operator
            if not is_first_condition and where_parts and where_parts[-1] not in ['AND', 'OR', 'NOT']:
                where_parts.append('AND')
            where_parts.append(condition)
            is_first_condition = False
        
        i += 1
    
    # Build JOIN clauses
    join_clauses = []
    if 'lawyers_fts' in fts_joins:
        # FTS5 join - use INNER JOIN for better performance with MATCH queries
        join_clauses.append("INNER JOIN lawyers_fts fts ON l.id = fts.rowid")
    if 'educations' in joins:
        join_clauses.append("LEFT JOIN educations e ON l.id = e.lawyer_id")
    if 'practices' in joins:
        join_clauses.append("LEFT JOIN practices p ON l.id = p.lawyer_id")
    if 'industries' in joins:
        join_clauses.append("LEFT JOIN industries ind ON l.id = ind.lawyer_id")
    if 'regions' in joins:
        join_clauses.append("LEFT JOIN regions r ON l.id = r.lawyer_id")
    if 'languages' in joins:
        join_clauses.append("LEFT JOIN languages lang ON l.id = lang.lawyer_id")
    
    # Build final SQL
    sql = "SELECT DISTINCT l.id, l.name, l.url FROM lawyers l"
    
    if join_clauses:
        sql += " " + " ".join(join_clauses)
    
    if where_parts:
        sql += " WHERE " + " ".join(where_parts)
    
    sql += " ORDER BY l.name"
    
    return sql, params


def execute_query(conn: sqlite3.Connection, sql: str, params: List[Any], 
                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Execute SQL query and return results.
    
    Args:
        conn: Database connection
        sql: SQL query string
        params: Query parameters
        limit: Maximum number of results
        
    Returns:
        List of result dictionaries with id, name, url
    """
    if limit:
        sql += f" LIMIT {limit}"
    
    cursor = conn.cursor()
    cursor.execute(sql, params)
    
    results = []
    for row in cursor:
        results.append({
            'id': row['id'],
            'name': row['name'],
            'url': row['url']
        })
    
    return results


def explain_query(conn: sqlite3.Connection, sql: str, params: List[Any]) -> str:
    """
    Get SQL query execution plan for debugging.
    
    Args:
        conn: Database connection
        sql: SQL query string
        params: Query parameters
        
    Returns:
        Execution plan as string
    """
    explain_sql = f"EXPLAIN QUERY PLAN {sql}"
    cursor = conn.cursor()
    cursor.execute(explain_sql, params)
    
    plan_lines = []
    for row in cursor:
        plan_lines.append(str(dict(row)))
    
    return "\n".join(plan_lines)

