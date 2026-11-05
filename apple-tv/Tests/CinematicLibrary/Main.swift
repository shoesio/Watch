import Foundation
@main struct Checks {
    static func main() throws {
        func programme(_ episodes:[[String:Any]],film:Bool=false,live:Bool=false,id:String="test",title:String="Test show",favouriteAt:Double=0)->Programme {
            let value:[String:Any] = ["id":id,"title":title,"favourite_at":favouriteAt,"live":live,"film":film,"recent":true,"favourite":true,"genres":[],"brands":[],"episodes":episodes]
            return try! JSONDecoder.watch.decode(Programme.self,from:JSONSerialization.data(withJSONObject:value))
        }
        func ep(_ id:String,_ season:String,_ number:Int,_ updated:Double=0)->[String:Any] {
            ["id":id,"title":id,"season":season,"episode_number":number,"updated_at":updated,"brands":[]]
        }
        precondition(programme([ep("label","Series 19",1)]).episodes[0].seasonNumber==19)
        precondition(programme([ep("label","Episodes",1)]).episodes[0].seasonNumber==nil)
        let seen=ep("seen","19",1,100)
        precondition(programme([seen,ep("new","19",2)]).hasNewEpisode)
        precondition(programme([seen,ep("new-season","20",1)]).hasNewEpisode)
        precondition(!programme([seen,ep("old","18",8)]).hasNewEpisode)
        precondition(!programme([seen,ep("already-watched","19",2,90)]).hasNewEpisode)
        precondition(!programme([seen,ep("special","Specials",1)]).hasNewEpisode)
        precondition(!programme([ep("unwatched","19",2)]).hasNewEpisode)
        precondition(!programme([seen,ep("new","19",2)],film:true).hasNewEpisode)
        precondition(!programme([seen,ep("new","19",2)],live:true).hasNewEpisode)
        precondition(programme([seen]).poster == nil,"Existing host libraries must decode without portrait artwork")
        let older=programme([],id:"a",title:"Alphabetical first",favouriteAt:50)
        let newer=programme([],id:"z",title:"Recent favourite",favouriteAt:100)
        precondition(BrowseOrdering.personal([older,newer],recommended:[]).first?.id=="z")
        let a=programme([],id:"a",title:"A"),z=programme([],id:"z",title:"Z")
        precondition(BrowseOrdering.personal([a,z],recommended:[z,a]).first?.id=="z")
        precondition(BrowseOrdering.personal([z,a],recommended:[]).first?.id=="z","A tie silently reverted to alphabetic order")
        precondition(programme([],title:"QI XL").editionLabel=="QI XL · Extended")
        precondition(programme([],title:"Taskmaster Bleeped").editionLabel=="Bleeped")
        print("Cinematic library checks passed: later episodes/seasons, watched editions, specials, films/live exclusion and backwards-compatible artwork")
    }
}
