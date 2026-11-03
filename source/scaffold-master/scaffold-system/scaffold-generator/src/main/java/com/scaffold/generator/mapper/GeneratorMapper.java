package com.scaffold.generator.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;
import java.util.Map;

@Mapper
public interface GeneratorMapper {

    @Select("""
            SELECT COUNT(*)
            FROM gen_table
            WHERE #{keyword} IS NULL OR #{keyword} = ''
               OR table_name LIKE CONCAT('%', #{keyword}, '%')
               OR table_comment LIKE CONCAT('%', #{keyword}, '%')
               OR class_name LIKE CONCAT('%', #{keyword}, '%')
            """)
    long countTables(@Param("keyword") String keyword);

    @Select("""
            SELECT id,
                   table_name AS tableName,
                   table_comment AS tableComment,
                   class_name AS className,
                   module_name AS module,
                   business_name AS businessName,
                   synced,
                   DATE_FORMAT(create_time, '%Y-%m-%d %H:%i') AS createTime
            FROM gen_table
            WHERE #{keyword} IS NULL OR #{keyword} = ''
               OR table_name LIKE CONCAT('%', #{keyword}, '%')
               OR table_comment LIKE CONCAT('%', #{keyword}, '%')
               OR class_name LIKE CONCAT('%', #{keyword}, '%')
            ORDER BY update_time DESC, id DESC
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectTables(@Param("keyword") String keyword, @Param("offset") int offset, @Param("pageSize") int pageSize);

    @Select("""
            SELECT t.table_name AS tableName,
                   t.table_comment AS tableComment,
                   CASE WHEN g.id IS NULL THEN 0 ELSE 1 END AS imported
            FROM information_schema.tables t
            LEFT JOIN gen_table g ON g.table_name = t.table_name
            WHERE t.table_schema = DATABASE()
              AND t.table_type = 'BASE TABLE'
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR t.table_name LIKE CONCAT('%', #{keyword}, '%')
                   OR t.table_comment LIKE CONCAT('%', #{keyword}, '%'))
            ORDER BY t.table_name
            """)
    List<Map<String, Object>> selectImportableTables(@Param("keyword") String keyword);

    @Select("""
            SELECT table_name AS tableName,
                   table_comment AS tableComment
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = #{tableName}
            """)
    Map<String, Object> selectDatabaseTable(@Param("tableName") String tableName);

    @Select("""
            SELECT column_name AS columnName,
                   data_type AS dataType,
                   column_type AS columnType,
                   column_comment AS columnComment,
                   is_nullable AS nullable,
                   ordinal_position AS sort
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = #{tableName}
            ORDER BY ordinal_position
            """)
    List<Map<String, Object>> selectDatabaseColumns(@Param("tableName") String tableName);

    @Select("""
            SELECT id,
                   table_name AS tableName,
                   table_comment AS tableComment,
                   class_name AS className,
                   module_name AS module,
                   business_name AS businessName,
                   synced
            FROM gen_table
            WHERE id = #{id}
            """)
    Map<String, Object> selectTableById(@Param("id") Long id);

    @Select("SELECT id FROM gen_table WHERE table_name = #{tableName}")
    Long selectTableIdByName(@Param("tableName") String tableName);

    @Insert("""
            INSERT INTO gen_table (table_name, table_comment, class_name, module_name, business_name, synced, create_by, update_by)
            VALUES (#{row.tableName}, #{row.tableComment}, #{row.className}, #{row.module}, #{row.businessName}, 1, #{username}, #{username})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertTable(@Param("row") Map<String, Object> row, @Param("username") String username);

    @Insert("""
            INSERT INTO gen_table_column (table_id, column_name, java_field, java_type, jdbc_type, column_comment,
                is_insert, is_edit, is_list, is_query, query_type, form_type, required, sort)
            VALUES (#{row.tableId}, #{row.columnName}, #{row.javaField}, #{row.javaType}, #{row.jdbcType}, #{row.columnComment},
                #{row.insert}, #{row.edit}, #{row.list}, #{row.query}, #{row.queryType}, #{row.formType}, #{row.required}, #{row.sort})
            """)
    int insertColumn(@Param("row") Map<String, Object> row);

    @Select("""
            SELECT id,
                   column_name AS col,
                   java_field AS javaField,
                   java_type AS javaType,
                   jdbc_type AS jdbcType,
                   column_comment AS comment,
                   is_insert AS `insert`,
                   is_edit AS edit,
                   is_list AS list,
                   is_query AS query,
                   query_type AS queryType,
                   form_type AS formType,
                   required
            FROM gen_table_column
            WHERE table_id = #{tableId}
            ORDER BY sort, id
            """)
    List<Map<String, Object>> selectColumns(@Param("tableId") Long tableId);

    @Update("""
            UPDATE gen_table
            SET table_comment = COALESCE(#{tableComment}, table_comment),
                synced = COALESCE(#{synced}, synced),
                update_by = #{username}
            WHERE id = #{id}
            """)
    int updateTable(@Param("id") Long id, @Param("tableComment") String tableComment,
                    @Param("synced") Integer synced, @Param("username") String username);
}
