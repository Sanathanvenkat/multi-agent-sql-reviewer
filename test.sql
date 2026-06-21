select * from users, orders
where users.id=orders.user_id
and YEAR(created_at)=2024
order by created_at